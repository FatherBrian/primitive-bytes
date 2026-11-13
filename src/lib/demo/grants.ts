// A small, in-browser version of Trellis's three checks, for the playground.
//
// It follows the same rules as the real engine (which compiles them to Cedar):
//   person  the person may use the tool themselves
//   agent   every tag on the tool is inside the agent's ceiling, and none is a `never` tag
//   task    the scope covers one of the tool's domains, every sensitive tag it carries,
//           and the action
// A field is masked when the agent's ceiling or the task scope doesn't cover its tags.

export const SENSITIVE = new Set(['pii']);

export interface Tool {
	id: string;
	label: string;
	action: 'read' | 'write';
	tags: string[];
	fields?: Record<string, string[]>;
}

export interface Person {
	id: string;
	label: string;
	domains: string[]; // what they can reach themselves
}

export interface Agent {
	id: string;
	label: string;
	ceiling: string[];
	never: string[];
	actions: string[];
}

export interface Template {
	id: string;
	label: string;
	scope: string[];
	actions: string[];
}

export const TOOLS: Tool[] = [
	{ id: 'ledger/journal_entries', label: 'Journal entries', action: 'read', tags: ['finance'], fields: { amount: [], approver_email: ['pii'] } },
	{ id: 'ledger/post_adjustment', label: 'Post adjustment', action: 'write', tags: ['finance'] },
	{ id: 'ledger/export_ledger', label: 'Export ledger', action: 'read', tags: ['finance', 'export_controlled'] },
	{ id: 'market/fx_rates', label: 'FX rates', action: 'read', tags: ['market-data'] },
	{ id: 'hr/headcount', label: 'Headcount', action: 'read', tags: ['hr'] },
	{ id: 'hr/payroll', label: 'Payroll', action: 'read', tags: ['hr'], fields: { team: [], salary: ['pii'] } },
	{ id: 'hr/performance_reviews', label: 'Performance reviews', action: 'read', tags: ['hr', 'pii'] },
	{ id: 'support/tickets', label: 'Support tickets', action: 'read', tags: ['support'], fields: { subject: [], customer_email: ['pii'] } },
	{ id: 'support/reply', label: 'Reply to ticket', action: 'write', tags: ['support'] },
	{ id: 'crm/accounts', label: 'CRM accounts', action: 'read', tags: ['customer'], fields: { company: [], phone: ['pii'] } },
];

export const PEOPLE: Person[] = [
	{ id: 'ana', label: 'Ana · finance and HR', domains: ['finance', 'market-data', 'hr', 'pii', 'export_controlled'] },
	{ id: 'ben', label: 'Ben · customer support', domains: ['support', 'customer', 'finance', 'pii'] },
];

export const AGENTS: Agent[] = [
	{ id: 'report-bot', label: 'report-bot', ceiling: ['finance', 'market-data', 'hr', 'pii'], never: ['export_controlled'], actions: ['read', 'write'] },
	{ id: 'support-bot', label: 'support-bot', ceiling: ['support', 'customer', 'pii'], never: ['hr'], actions: ['read', 'write'] },
];

export const TEMPLATES: Template[] = [
	{ id: 'close', label: 'Q3 close', scope: ['finance', 'market-data'], actions: ['read', 'write'] },
	{ id: 'headcount', label: 'Headcount review', scope: ['hr'], actions: ['read'] },
	{ id: 'headcount-pii', label: 'Headcount review, with pii', scope: ['hr', 'pii'], actions: ['read'] },
	{ id: 'escalation', label: 'Customer escalation', scope: ['support', 'customer', 'pii'], actions: ['read', 'write'] },
];

export interface Check {
	ok: boolean;
	why: string;
}

export interface Decision {
	allowed: boolean;
	person: Check;
	agent: Check;
	task: Check;
	masked: Record<string, string>;
}

const list = (tags: Iterable<string>) => [...tags].join(', ');

export function decide(person: Person, agent: Agent, t: Template, tool: Tool): Decision {
	const tags = new Set(tool.tags);
	const domains = tool.tags.filter((x) => !SENSITIVE.has(x));

	const name = person.label.split(' ')[0];
	const unreachable = tool.tags.filter((x) => !person.domains.includes(x));
	const personCheck: Check = unreachable.length
		? { ok: false, why: `${name} has no access to ${list(unreachable)}` }
		: { ok: true, why: `${name} has access` };

	const never = tool.tags.filter((x) => agent.never.includes(x));
	const outside = tool.tags.filter((x) => !agent.ceiling.includes(x) && !agent.never.includes(x));
	let agentCheck: Check;
	if (never.length) agentCheck = { ok: false, why: `${agent.label} may never touch ${list(never)}` };
	else if (!agent.actions.includes(tool.action)) agentCheck = { ok: false, why: `${agent.label} can't ${tool.action}` };
	else if (outside.length) agentCheck = { ok: false, why: `${agent.label}'s ceiling doesn't include ${list(outside)}` };
	else agentCheck = { ok: true, why: 'inside its ceiling' };

	const scopeDomains = t.scope.filter((x) => !SENSITIVE.has(x));
	const unnamed = [...tags].filter((x) => SENSITIVE.has(x) && !t.scope.includes(x));
	let taskCheck: Check;
	if (!t.actions.includes(tool.action)) taskCheck = { ok: false, why: `the task doesn't allow ${tool.action}` };
	else if (!domains.some((x) => scopeDomains.includes(x)))
		taskCheck = { ok: false, why: `the task covers ${list(t.scope)}, not ${list(domains)}` };
	else if (unnamed.length) taskCheck = { ok: false, why: `it's ${list(unnamed)}, and the task doesn't name ${list(unnamed)}` };
	else taskCheck = { ok: true, why: 'inside the task' };

	const allowed = personCheck.ok && agentCheck.ok && taskCheck.ok;
	const masked: Record<string, string> = {};
	if (allowed) {
		for (const [field, own] of Object.entries(tool.fields ?? {})) {
			const ftags = [...new Set([...own, ...tool.tags])];
			const notInCeiling = ftags.filter((x) => !agent.ceiling.includes(x));
			const notInScope = ftags.filter((x) => SENSITIVE.has(x) && !t.scope.includes(x));
			if (notInCeiling.length) masked[field] = `${agent.label}'s ceiling has no ${list(notInCeiling)}`;
			else if (notInScope.length) masked[field] = `the task doesn't name ${list(notInScope)}`;
		}
	}
	return { allowed, person: personCheck, agent: agentCheck, task: taskCheck, masked };
}

// -- a hash-chained ledger, like Trellis's (without the signatures) ---------------------------

export interface Entry {
	seq: number;
	at: string;
	body: Record<string, unknown>;
	prev: string;
	hash: string;
}

async function sha256(text: string): Promise<string> {
	const bytes = new TextEncoder().encode(text);
	const digest = await crypto.subtle.digest('SHA-256', bytes);
	return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, '0')).join('');
}

const canonical = (e: Omit<Entry, 'hash'>) => JSON.stringify({ seq: e.seq, at: e.at, body: e.body, prev: e.prev });

export async function append(chain: Entry[], body: Record<string, unknown>): Promise<Entry> {
	const prev = chain.length ? chain[chain.length - 1].hash : '0'.repeat(64);
	const partial = { seq: chain.length + 1, at: new Date().toISOString(), body, prev };
	const entry = { ...partial, hash: await sha256(canonical(partial)) };
	chain.push(entry);
	return entry;
}

/** The first entry that doesn't check out, or null if the chain is intact. */
export async function verify(chain: Entry[]): Promise<{ seq: number; why: string } | null> {
	let prev = '0'.repeat(64);
	for (const e of chain) {
		if (e.prev !== prev) return { seq: e.seq, why: "its link to the entry before doesn't match" };
		if ((await sha256(canonical(e))) !== e.hash) return { seq: e.seq, why: 'its contents were changed after it was written' };
		prev = e.hash;
	}
	return null;
}
