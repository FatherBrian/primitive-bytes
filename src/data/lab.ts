// What's in the Lab. Add a demo here and it shows up on the home page.

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
	{
		path: '/lab/drift/',
		title: 'MCP drift watch',
		blurb:
			'Every day, reef.lock checks public MCP servers for tools whose descriptions or schemas changed, and publishes the diffs.',
		kind: 'drift',
		section: 'AI',
	},
] as const;
