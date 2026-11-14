# wp-to-next

WordPress to Next.js migration (synthetic portfolio repository).

## Stack

- Next.js
- WordPress
- headless CMS
- SEO

## Setup

```bash
make install
make test
```

## Architecture

The service kept WordPress as the editor and moved the front end to Next.js with redirects for every old URL. See `src/` for the pipeline entry points.
