// What's in the Lab. Add a project here and it shows up.

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
		path: '/lab/chat/',
		title: 'Agent chat',
		blurb:
			'Chat with an agent wired to real MCP servers, some of them hostile. Put a gateway in front, pin its tools, and watch every call, view and ledger entry.',
		kind: 'chat',
		section: 'AI',
	},
	{
		path: '/lab/sql/',
		title: 'SQL playground',
		blurb:
			'A full DuckDB engine running in your browser. Query sample data or drop in your own CSV or Parquet, chart the results, read the plan, and export Parquet.',
		kind: 'sql',
		section: 'Data',
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
		demo: { label: 'Try task grants', path: '/lab/chat/?scenario=payroll-headcount' },
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
		demo: { label: 'Try the lock', path: '/lab/chat/?scenario=rug-pull-locked' },
	},
	{
		name: 'Primitive Bytes',
		blurb: 'This site. Astro, a little CSS, an agent chat, and a database that runs in your browser.',
		status: 'Live',
		tags: ['Astro', 'TypeScript'],
		links: [{ label: 'GitHub', href: 'https://github.com/FatherBrian/primitive-bytes' }],
	},
];
