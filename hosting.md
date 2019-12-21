The code in this repo helps you extract content from a Zulip
instance and build the basic HTML structure, but it leaves it
to you to actually host the data on some server.

In other words, Zulip is not opinionated about you serve
the HTML (and in some ways the entire mission of this project
is to empower you to put your data where you want).

### General procedures

No matter where you host your data, you will typically
have a "PROD" install.  This will involve more detailed
updates to `settings.py` than you probably made for local
testing.  Here is a typical diff:

~~~
<     # site_url = 'example.com'
<     raise Exception("You need to configure site_url for prod")
---
>     site_url = 'https://showell.github.io/'
46,47c45
<     # Set this according to how you serve your prod assets.
<     zulip_icon_url = None
---
>     zulip_icon_url = 'http://showell.github.io/assets/img/zulip2.png'
82,87c80
<     raise Exception('''
<         You need to set html_directory for prod, and it
<         should be a different location than DEBUG mode,
<         since files will likely have different urls in
<         anchor tags.
<         ''')
---
>     html_directory = Path('../website/archive')
~~~


To build your site with prod settings, do this:

    `PROD_ARCHIVE=1 python archive.py -b`

You will also want to copy layouts and assets to your production
directory.  These include:

* layouts
* zulip2.png

### Jekyll

[Jekyll](https://jekyllrb.com/) is a popular tool for
serving static content.

The archive script generates index pages in markdown that are
designed for a Jekyll build, so you can do something like this
from within this directory (where you checked out code):

```
gem install jekyll bundler
jekyll serve
```

With the default configuration you should be able to see
your archive at http://127.0.0.1:4000/archive/

If you have a large archive that you update regularly,
you may want to run `jekyll serve --incremental`.

### GitHub

You can use GitHub Pages to serve your HTML.  We recommend
configuring your `md_root` to point into your local copy of
your `username.github.io` repo (e.g. `alice.github.io`) and
then push from there.

Some customers will want to just use the same repo for both
this tooling and the content from their Zulip instance.  We
don't recommend this approach long term, since it can complicate
staying up to date with patches from this repo.  If you are
still interested in this approach, despite the warnings, you
may find the `github.py` script to be useful.
