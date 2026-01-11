# ai-skills

A collection of useful AI skills in standard skill file layout.  See https://agentskills.io for the
official skills specification and documentation.

This repo contains the following skills.  Each `.skill` package file has a matching directory
containing the files in the skill package (e.g., the files for `myskill.skill` are in directory
`myskill`).

* [**load-skill.skill**](load-skill.skill): A skill to load and install other skill files.  Usage: `/load-skill SKILLFILE`

* [**bluesky.skill**](bluesky.skill): A skill to post, read, search, reply, read notifications, and read threads on BlueSky.

* [**drawio.skill**](drawio.skill): A skill to generate a draw.io diagram from a text description.

* [**transcript-saver.skill**](transcript-saver.skill): A skill by Simon Willison to save an HTML transcript of a conversation.
