# Contributing to the blog

We welcome contributions from all members of the cycling club to our blog!
Here we describe the basic workflow of contributing a blog post.

TL;DR This is a standard git+hugo workflow. If you have written a blog in e.g. google docs and want someone to upload it to the website for you, please contact the website officer for the club

## Setup

To contribute a blog post you will open a PR to this repository. To do this you must have the following items configured:
1. Create a github account and a fork of this repository
2. Install git and clone the repository fork
3. Install [Hugo](https://gohugo.io/installation/) to build and test the website locally

To confirm that the installation is working, run `hugo serve` in your local copy of the repository and preview the website on the `localhost` url 

## Starting a new blog post

Imagine that you participated in a fun cyclocross race with our club and want to write a blog post about it.
To start a new blog post, our workflow is to open a pull request (PR) with your blog to the main repository.
You will have to create a branch of `main` and write your blog in the branch.
Start and switch to a new branch called `cx-race` with the command `git checkout -b cx-race`.
Blog posts in Hugo are written as Markdown files and Hugo will generate the file for you.
Simply type `hugo new content content/blog/cx-race.md` to create the new markdown file `cx-race.md` in the `content/blog` folder of the repository.

The file includes a header with the basic information about the post. We ask to include some additional fields in the header, as in this sample header
```
---
title: "Winter Training Camp 2026"
date: 2026-02-25T09:00:00-05:00
author: "Aaron Vliet"
categories: ["Training", "Road", "Rides", "Photos"]
tags: ["training camp", "road", "2026", "Tucson"]
image: "/img/blog/winter-training-camp-2026.jpg"
---
```
With this markdown file setup, you can write your story in the markdown file!

## Adding images

Upload your images to the assets of the website in a new folder for your blog, e.g. `assets/img/blog/posts/cx-race/image.jpg`.

Then include the image in your markdown file using the standard markdown syntax `![](/img/blog/posts/cx-race/image.jpg)` pointing to file as though `/` were `assets`.

To emulate captions, _emphasize_ the caption text.

## Opening the PR

Before opening the PR, run `hugo serve` to preview the website and make sure that your blog post renders as you like it.
Once you are happy with your post, you will `git add` the new files for your post (make sure you check `git status` to be sure you include all of them).
Then `git commit -m 'new cx race blog post'` the changes on your `cx-race` branch.
Next, `git push fork cx-race` to upload your post to the github fork you created.
Finally, visit the github repository of the website and click the pull requests tab.
You should be able to see a button to open a pull request from your recently created branch with recent changes.
Continue there and create the pull request.

## Reviewing the PR

The website officer of the club will review your post, possibly making editorial suggestions, revising the header containing blog metadata, or 