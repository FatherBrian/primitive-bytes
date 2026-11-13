import { type CollectionEntry, getCollection } from 'astro:content';
import { url } from '../url';

export type Post = CollectionEntry<'blog'>;
export type Note = CollectionEntry<'notes'>;

/** A post or a note, in the shape the lists and the feed need. */
export interface Entry {
	kind: 'post' | 'note';
	id: string;
	href: string;
	title: string;
	description: string;
	pubDate: Date;
	tags: string[];
	body: string;
}

const published = <T extends { data: { draft: boolean } }>(e: T) =>
	import.meta.env.DEV || !e.data.draft;

const newestFirst = (a: { pubDate: Date }, b: { pubDate: Date }) =>
	b.pubDate.valueOf() - a.pubDate.valueOf();

/** Every published post, newest first. */
export async function allPosts(): Promise<Post[]> {
	return (await getCollection('blog'))
		.filter(published)
		.sort((a, b) => newestFirst(a.data, b.data));
}

/** Every published note, newest first. */
export async function allNotes(): Promise<Note[]> {
	return (await getCollection('notes'))
		.filter(published)
		.sort((a, b) => newestFirst(a.data, b.data));
}

export function postEntry(p: Post): Entry {
	return {
		kind: 'post',
		id: p.id,
		href: url(`/blog/${p.id}/`),
		title: p.data.title,
		description: p.data.description,
		pubDate: p.data.pubDate,
		tags: p.data.tags,
		body: p.body ?? '',
	};
}

export function noteEntry(n: Note): Entry {
	return {
		kind: 'note',
		id: n.id,
		href: url(`/notes/${n.id}/`),
		title: n.data.title,
		description: n.data.description ?? excerpt(n.body),
		pubDate: n.data.pubDate,
		tags: n.data.tags,
		body: n.body ?? '',
	};
}

/** Posts and notes together, newest first. */
export async function allEntries(): Promise<Entry[]> {
	const [posts, notes] = await Promise.all([allPosts(), allNotes()]);
	return [...posts.map(postEntry), ...notes.map(noteEntry)].sort(newestFirst);
}

/** Minutes to read, at about 230 words a minute. */
export function readingTime(body: string | undefined): number {
	const words = (body ?? '').replace(/```[\s\S]*?```/g, ' ').split(/\s+/).filter(Boolean).length;
	return Math.max(1, Math.round(words / 230));
}

/** The first sentence or so of a body, as plain text, for notes without a description. */
export function excerpt(body: string | undefined, max = 160): string {
	const text = (body ?? '')
		.replace(/```[\s\S]*?```/g, ' ')
		.replace(/!\[[^\]]*\]\([^)]*\)/g, ' ')
		.replace(/\[([^\]]*)\]\([^)]*\)/g, '$1')
		.replace(/^#+\s+/gm, '')
		.replace(/[*_`>#-]/g, '')
		.replace(/\s+/g, ' ')
		.trim();
	if (text.length <= max) return text;
	const cut = text.slice(0, max);
	return `${cut.slice(0, cut.lastIndexOf(' ')).replace(/[,.;:]$/, '')}…`;
}
