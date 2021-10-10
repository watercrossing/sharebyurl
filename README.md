# Share by URL

This tool allows you to quickly create unique and non-guessable share links for files hosted on your local machine.

`sharebylink image.jpg` will create a new directory (for example, `var/www/html/s/debkxsyfz2/`) and create a symlink in that folder for `image.jpg`. With the correct server configuration, this file is now accessible from, say `mydomain.com/s/debkxsyfz2/image.jpg`.

## Prerequesites

* A machine with a webserver, preferably publicly accessible.
* Unix. This should run on Windows too, but this is not very feasible since symlinking requires elevated privileges. 


## Installation

* preferably using [`pipx`](https://pypa.github.io/pipx/): pipx install git+https://github.com/watercrossing/sharebyurl.git
* `python3 -m pip install --user git+https://github.com/watercrossing/sharebyurl.git



The code structure is heavily inspired by `pipx`. 

## TODO list

* add the features that are still 'to be completed'
* proper tests, linting, types, code reorganisation
* put this on pypi

## Ideas

* move `.htaccess` files into each source directory to selectively enable / disable directory listing
* set a `systemd` timer for expiration of shares
