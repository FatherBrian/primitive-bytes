import rss from '@astrojs/rss';
import { SITE_DESCRIPTION, SITE_TITLE } from '../consts';
import { allEntries } from '../lib/posts';

// Posts and notes together, newest first.
export async function GET(context) {
	const entries = await allEntries();
	return rss({
		title: SITE_TITLE,
		description: SITE_DESCRIPTION,
		site: context.site,
		items: entries.map((e) => ({
			title: e.kind === 'note' ? `Note: ${e.title}` : e.title,
			description: e.description,
			pubDate: e.pubDate,
			categories: e.tags,
			link: e.href,
		})),
	});
}
