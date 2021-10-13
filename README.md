# Share by URL

This tool allows you to quickly create unique and non-guessable share links for files hosted on your local machine.

`sharebylink image.jpg` will create a new directory (for example, `debkxsyfz2` in `/var/www/html/s`) and create a symlink in that folder for `image.jpg`. With the correct server configuration, this file is now accessible from, say `mydomain.com/s/debkxsyfz2/image.jpg`.

The `-s` switch allows you to specify a name for the share, making links more recognisable and reusable: 
`sharebylink -s london21 image.jpg` creates a directory `london21-9me2gkistk` and symlinks `image.jpg` in that directory. Later on `sharebylink -s london21-9me2gkistk image2.jpg` can be used to add more images to that folder. This project provides bash/zsh, fish, and tcsh completion (using [argcomplete](https://pypi.org/project/argcomplete/)) to save you from typing the random string part.

The code structure is heavily inspired by [`pipx`](https://pypa.github.io/pipx/). 

## Prerequesites

* A machine with a webserver, preferably publicly accessible.
* Unix. This should run on Windows too, but this is not very feasible since symlinking requires elevated privileges. Maybe there is way to ask for priviledges when the command is invoked (runas?), but I haven't looked into how that can be integrated into a python program. Who runs a webserver on Windows anyway?


## Installation

* preferably using [`pipx`](https://pypa.github.io/pipx/): pipx install git+https://github.com/watercrossing/sharebyurl.git
* `python3 -m pip install --user git+https://github.com/watercrossing/sharebyurl.git

The code structure is heavily inspired by [`pipx`](https://pypa.github.io/pipx/). 

## Enabling autocomplete


### Example apache htdocs configuration



## TODO list

* add the features that are still 'to be completed'
* proper tests, linting, types, code reorganisation
* put this on pypi

## Ideas

* move `.htaccess` files into each source directory to selectively enable / disable directory listing
* set a `systemd` timer for expiration of shares
