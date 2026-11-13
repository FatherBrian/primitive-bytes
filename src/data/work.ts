// What's on the Work page. Add a project here and it shows up.

export interface Project {
	name: string;
	blurb: string;
	status: string;
	tags: string[];
	links: { label: string; href: string }[];
	demo?: { label: string; path: string };
}

export const DEMOS = [
	{
		path: '/work/grant-playground/',
		title: 'Grant playground',
		blurb:
			'Pick a person, an agent and a task, and watch three checks decide every tool call. Then tamper with the ledger and see it get caught.',
		kind: 'grants',
	},
	{
		path: '/work/reef-lock/',
		title: 'reef lock, live',
		blurb:
			'A server quietly rewrites a tool description to steer your agent. The lockfile notices, shows the diff and hides the tool.',
		kind: 'lock',
	},
] as const;

export const PROJECTS: Project[] = [
	{
		name: 'Trellis',
		blurb:
			'Delegated access control for AI agents: every call needs the person, the agent and the task to agree, and every decision lands in a tamper-evident ledger.',
		status: 'v0.1.1 on PyPI',
		tags: ['Python', 'Cedar', 'Agents & MCP', 'AI governance'],
		links: [
			{ label: 'GitHub', href: 'https://github.com/FatherBrian/trellis' },
			{ label: 'PyPI', href: 'https://pypi.org/project/trellisd/' },
		],
		demo: { label: 'Grant playground', path: '/work/grant-playground/' },
	},
	{
		name: 'Reef',
		blurb:
			'Right-size and pin what your agents can reach. reef lock pins what every MCP tool says and fails CI when a server changes it; as a gateway, each agent sees only the tools its grant allows.',
		status: 'v0.1.1 on PyPI',
		tags: ['Python', 'MCP', 'Platform building'],
		links: [
			{ label: 'GitHub', href: 'https://github.com/FatherBrian/trellis/tree/main/reef' },
			{ label: 'PyPI', href: 'https://pypi.org/project/reef-mcp/' },
		],
		demo: { label: 'reef lock, live', path: '/work/reef-lock/' },
	},
	{
		name: 'Primitive Bytes',
		blurb: 'This site. Astro, a little CSS, and demos that run entirely in your browser.',
		status: 'Live',
		tags: ['Astro', 'TypeScript'],
		links: [{ label: 'GitHub', href: 'https://github.com/FatherBrian/primitive-bytes' }],
	},
];
