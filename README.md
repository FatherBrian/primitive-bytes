# Primitive Bytes

A blog about data and AI, posted sometimes, plus random things I build.

Live at <https://fatherbrian.github.io/primitive-bytes/>. Built with [Astro](https://astro.build)
and deployed to GitHub Pages on every push to `main`.

## Write something

```bash
npm run new note "Title"    # a short note about anything: src/content/notes/
npm run new post "Title"    # a longer post: src/content/blog/ (starts as a draft)
```

Edit the file it prints, then commit and push. The site rebuilds in about a minute.

- **Posts** need a `description` (one sentence, shown under the title and in lists) and
  usually `tags`, like `['Data governance']`.
- **Notes** need only a `title` and `pubDate`. Add a `description` if you want one;
  otherwise the first lines of the note are used in lists and the feed.
- **Drafts:** `draft: true` keeps a post or note off the live site. It still shows in
  `npm run dev`, so you can preview it.

## Run it locally

```bash
npm install
npm run dev      # http://localhost:4321/primitive-bytes/
npm run build    # into dist/
```
