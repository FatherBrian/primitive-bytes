// Turns demo API events into transcript steps. Shared by live runs and saved-run replays.
import { configureViews, mountView } from './views';

export { configureViews };
export type Ev = Record<string, any>;

const esc = (s: unknown) =>
	String(s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]!);

function add(steps: HTMLElement, cls: string, html: string) {
	const li = document.createElement('li');
	li.className = cls;
	li.innerHTML = html;
	steps.appendChild(li);
	return li;
}

/** Adds the step for one event. Returns true if the event drew something. */
export function showEvent(steps: HTMLElement, e: Ev): boolean {
	switch (e.type) {
		case 'setup':
			add(steps, 'setup', `<b>${esc(e.summary)}</b><span>Asked: “${esc(e.task)}”</span>`);
			return true;
		case 'tools':
			add(
				steps,
				'tools',
				`<b>Tools the agent can see</b>${e.tools.map((t: Ev) => `<span><code>${esc(t.name)}</code> ${esc(t.description)}</span>`).join('') || '<span>none</span>'}`,
			);
			return true;
		case 'thinking':
			add(steps, 'thinking', `<b>Thinking</b><span>${esc(e.text)}</span>`);
			return true;
		case 'text':
			add(steps, 'text', `<b>Agent</b><span class="answer">${esc(e.text)}</span>`);
			return true;
		case 'tool_call':
			add(steps, 'call', `<b>Calls <code>${esc(e.name)}</code></b><span><code>${esc(JSON.stringify(e.input))}</code></span>`);
			return true;
		case 'tool_result': {
			const li = add(
				steps,
				e.is_error ? 'result error' : 'result',
				`<b>${esc(e.name)} returned</b><span><code>${esc(String(e.text).slice(0, 400))}</code></span>`,
			);
			if (e.ui && e.data) void mountView(li, e.ui, e.input ?? {}, e.data);
			return true;
		}
		case 'ledger':
			add(
				steps,
				'ledger',
				`<b>Ledger</b>${e.entries.map((l: Ev) => `<span>#${esc(l.seq)} ${esc(l.what)}${l.why ? ` · ${esc(l.why)}` : ''}</span>`).join('')}`,
			);
			return true;
		case 'server':
			add(
				steps,
				'server',
				`<b>What the ${esc(e.server)} server actually received</b><span>${e.calls.length ? e.calls.map((c: Ev) => `<code>${esc(c.tool)}</code>`).join(' ') : 'nothing'}</span>`,
			);
			return true;
		case 'error':
			add(steps, 'error', `<b>Stopped</b><span>${esc(e.message)}</span>`);
			return true;
		default:
			return false;
	}
}

/**
 * Start a live run and hand each streamed event to onEvent. Resolves when the stream ends;
 * throws an Error with a message fit to show if the server refuses or can't be reached.
 */
export async function streamRun(api: string, body: unknown, onEvent: (e: Ev) => void): Promise<void> {
	let res: Response;
	try {
		res = await fetch(`${api}/api/run`, {
			method: 'POST',
			headers: { 'content-type': 'application/json' },
			body: JSON.stringify(body),
		});
	} catch {
		throw new Error("Couldn't reach the demo server. Try again in a minute.");
	}
	if (!res.ok || !res.body) {
		const err = await res.json().catch(() => ({}));
		throw new Error(err.error ?? `The demo server said ${res.status}.`);
	}
	const reader = res.body.getReader();
	const decoder = new TextDecoder();
	let buffer = '';
	for (;;) {
		const { value, done } = await reader.read();
		if (done) break;
		buffer += decoder.decode(value, { stream: true });
		let cut;
		while ((cut = buffer.indexOf('\n\n')) >= 0) {
			const chunk = buffer.slice(0, cut);
			buffer = buffer.slice(cut + 2);
			if (chunk.startsWith('data: ')) onEvent(JSON.parse(chunk.slice(6)));
		}
	}
}

/** A share link and copy button for a finished run. */
export function shareLink(into: HTMLElement, id: string) {
	const link = runLink(id);
	const a = document.createElement('a');
	a.href = link;
	a.textContent = 'Link to this run';
	const copy = document.createElement('button');
	copy.type = 'button';
	copy.className = 'copy';
	copy.textContent = 'Copy link';
	copy.addEventListener('click', () => {
		navigator.clipboard?.writeText(link).then(() => (copy.textContent = 'Copied'));
	});
	into.replaceChildren(a, copy);
	into.hidden = false;
}

/** Where a saved run can be replayed. */
export function runLink(id: string): string {
	const base = import.meta.env.BASE_URL.replace(/\/$/, '');
	return `${location.origin}${base}/lab/run/?id=${encodeURIComponent(id)}`;
}
