// npm run new note "Title"   → src/content/notes/<slug>.md
// npm run new post "Title"   → src/content/blog/<slug>.md
//
// Writes the file with today's date and the frontmatter filled in, then prints its path.

import { existsSync, mkdirSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';

const [kind, ...words] = process.argv.slice(2);
const title = words.join(' ').trim();
const dirs = { note: 'src/content/notes', post: 'src/content/blog' };

if (!(kind in dirs) || !title) {
	console.error('Usage: npm run new note "Title"   or   npm run new post "Title"');
	process.exit(1);
}

const slug = title
	.toLowerCase()
	.normalize('NFKD')
	.replace(/[̀-ͯ]/g, '')
	.replace(/[^a-z0-9]+/g, '-')
	.replace(/^-+|-+$/g, '')
	.slice(0, 60)
	.replace(/-+$/, '');
const now = new Date();
const date = [now.getFullYear(), now.getMonth() + 1, now.getDate()]
	.map((n, i) => (i === 0 ? String(n) : String(n).padStart(2, '0')))
	.join('-');
const file = join(dirs[kind], `${slug}.md`);

if (existsSync(file)) {
	console.error(`${file} already exists. Pick another title, or edit that file.`);
	process.exit(1);
}

const quote = (s) => `'${s.replace(/'/g, "''")}'`;
const frontmatter =
	kind === 'post'
		? [
				`title: ${quote(title)}`,
				`description: 'One sentence on what this post argues.'`,
				`pubDate: '${date}'`,
				`tags: ['Data governance']`,
				`draft: true`,
			]
		: [`title: ${quote(title)}`, `pubDate: '${date}'`, `tags: []`, `# draft: true`];

mkdirSync(dirs[kind], { recursive: true });
writeFileSync(file, `---\n${frontmatter.join('\n')}\n---\n\nWrite here.\n`);
console.log(`Created ${file}`);
if (kind === 'post') console.log('It starts as a draft: remove `draft: true` to publish it.');
else console.log('It publishes on the next push. Uncomment `draft: true` to hold it back.');
