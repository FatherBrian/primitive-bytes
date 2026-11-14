// Turns demo API events into transcript steps. Shared by live runs and saved-run replays.
export type Ev = Record<string, any>;

const esc = (s: unknown) =>
	String(s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]!);

function add(steps: HTMLElement, cls: string, html: string) {
	const li = document.createElement('li');
	li.className = cls;
	li.innerHTML = html;
	steps.appendChild(li);
}

/** Adds the step for one event. Returns true if the event drew something. */
export function showEvent(steps: HTMLElement, e: Ev): boolean {
	switch (e.type) {
		case 'setup':
			add(steps, 'setup', `<b>${esc(e.summary)}</b><span>Task: “${esc(e.task)}”</span>`);
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
		case 'tool_result':
			add(
				steps,
				e.is_error ? 'result error' : 'result',
				`<b>${esc(e.name)} returned</b><span><code>${esc(String(e.text).slice(0, 400))}</code></span>`,
			);
			return true;
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

/** Where a saved run can be replayed. */
export function runLink(id: string): string {
	const base = import.meta.env.BASE_URL.replace(/\/$/, '');
	return `${location.origin}${base}/lab/run/?id=${encodeURIComponent(id)}`;
}
