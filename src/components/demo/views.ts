// A small MCP Apps host: renders a tool's ui:// view in a sandboxed iframe and speaks the
// view side of the protocol over postMessage JSON-RPC.
//
// The Lab's host policy, shown to the visitor as it happens:
// - tools/call from a view is refused (this host doesn't offer serverTools);
// - ui/message is shown to you, never passed to the model;
// - ui/open-link is shown, not opened;
// - the view's own network requests are blocked by a content security policy.
// The iframe gets only allow-scripts, so it runs in an opaque origin, apart from this page.

type J = Record<string, any>;

let API = '';
const cache = new Map<string, Promise<string>>();

/** Where to fetch views from (the demo API). Call once per page. */
export function configureViews(api: string) {
	API = api;
}

const CSP =
	"default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data:; font-src data:";

function html(uri: string): Promise<string> {
	if (!cache.has(uri)) {
		cache.set(
			uri,
			fetch(`${API}/api/world/ui?uri=${encodeURIComponent(uri)}`).then((r) => {
				if (!r.ok) throw new Error(`no view at ${uri}`);
				return r.text();
			}),
		);
	}
	return cache.get(uri)!;
}

function theme(): 'light' | 'dark' {
	const set = document.documentElement.dataset.theme;
	if (set === 'light' || set === 'dark') return set;
	return matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}

function noteLine(list: HTMLElement, kind: string, text: string, detail?: string) {
	const li = document.createElement('li');
	li.className = kind;
	const b = document.createElement('b');
	b.textContent = text;
	li.append(b);
	if (detail) {
		const span = document.createElement('span');
		span.textContent = detail;
		li.append(span);
	}
	list.append(li);
	list.hidden = false;
}

/** Render a view for one tool result into `into`. */
export async function mountView(into: HTMLElement, uri: string, args: J, result: J) {
	if (!API) return;
	const box = document.createElement('div');
	box.className = 'mcp-view';
	const label = document.createElement('p');
	label.className = 'mcp-view-label';
	label.textContent = `View · ${uri}`;
	const frame = document.createElement('iframe');
	frame.setAttribute('sandbox', 'allow-scripts');
	frame.setAttribute('title', `MCP App view ${uri}`);
	frame.style.height = '180px';
	const notes = document.createElement('ul');
	notes.className = 'mcp-view-notes';
	notes.hidden = true;
	box.append(label, frame, notes);
	into.append(box);

	let source: string;
	try {
		source = await html(uri);
	} catch {
		label.textContent = `View · ${uri} (couldn't load it)`;
		frame.remove();
		return;
	}
	// The host, not the view, decides what the view may load or reach.
	frame.srcdoc = source.replace('<head>', `<head><meta http-equiv="Content-Security-Policy" content="${CSP}">`);

	const send = (msg: J) => frame.contentWindow?.postMessage({ jsonrpc: '2.0', ...msg }, '*');
	const reply = (id: unknown, result?: J, error?: J) => send(error ? { id, error } : { id, result });

	function onMessage(e: MessageEvent) {
		if (e.source !== frame.contentWindow) return; // only this view, nothing else
		const m = e.data;
		if (!m || m.jsonrpc !== '2.0' || typeof m.method !== 'string') return;
		const p = m.params ?? {};
		switch (m.method) {
			case 'ui/initialize':
				reply(m.id, {
					protocolVersion: 'draft',
					hostInfo: { name: 'Primitive Bytes Lab', version: '1' },
					hostCapabilities: {},
					hostContext: { theme: theme(), displayMode: 'inline', platform: 'web' },
				});
				break;
			case 'ui/notifications/initialized':
				send({ method: 'ui/notifications/tool-input', params: { arguments: args } });
				send({ method: 'ui/notifications/tool-result', params: { content: [], structuredContent: result } });
				break;
			case 'ui/notifications/size-changed':
				if (typeof p.height === 'number') frame.style.height = `${Math.min(Math.max(p.height, 60), 520)}px`;
				break;
			case 'tools/call':
				noteLine(notes, 'blocked', `The view asked the host to call ${p.name ?? 'a tool'}. Refused.`, JSON.stringify(p.arguments ?? {}).slice(0, 240));
				reply(m.id, undefined, { code: -32601, message: 'This host does not let views call tools.' });
				break;
			case 'ui/message': {
				const text = (p.content ?? []).map((c: J) => c.text ?? '').join(' ').slice(0, 300);
				noteLine(notes, 'shown', 'The view tried to add a message to the chat. Shown to you, not sent to the model:', text);
				reply(m.id, undefined, { code: -32601, message: 'Messages from views are shown to the user only.' });
				break;
			}
			case 'ui/open-link':
				noteLine(notes, 'shown', 'The view asked to open a link. Not opened:', String(p.url ?? ''));
				reply(m.id, undefined, { code: -32601, message: 'Links are not opened from views.' });
				break;
			default:
				if (m.id !== undefined) reply(m.id, undefined, { code: -32601, message: `${m.method} isn't supported by this host.` });
		}
	}
	addEventListener('message', onMessage);
	// Stop listening once the view is gone (a new run clears the transcript).
	const gone = new MutationObserver(() => {
		if (!box.isConnected) {
			removeEventListener('message', onMessage);
			gone.disconnect();
		}
	});
	gone.observe(document.body, { childList: true, subtree: true });
}
