#!/bin/bash

# use tee, otherwise shellcheck complains
sudo journalctl --boot | tee journal-log >/dev/null
