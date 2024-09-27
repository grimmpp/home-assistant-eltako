#!/bin/bash

# Install from outside. Copy file and run it in HA.

# Function to display commands
exe() { echo "\$ ${@/eval/}" ; "$@" ; }

echo -e "\nInstall custom component for Eltako Baureihe 14\n"

current_branch=$(git branch --show-current)
ehco "Running on branch $current_branch\n"

repo_name="home-assistant-eltako"
if [[ $(pwd) != *"$repo_name"* ]]; then
    repo_name="https://github.com/grimmpp/home-assistant-eltako.git"
    echo -e "Download repository $repo_name"
    exe git clone $repo_name
else 
    exe git pull
fi

custom_components="/root/config/custom_components"
eltako_dir="$custom_components/eltako"
if [ -d "$eltako_dir" ]; then
    echo -e "\nDelete directory $eltako_dir"
    exe rm -r $eltako_dir
fi

repo_dir=""
if [[ $(pwd) != *"$repo_name"* ]]; then
    repo_dir="/home-assistant-eltako"
fi

echo -e "\nCopy new folder into $eltako_dir"
exe mkdir -p $eltako_dir
exe cp -r .$repo_dir/custom_components/eltako $custom_components

#echo -e "\nRemove leftovers from repo home-assistant-eltko"
#exe rm -r .$repo_dir

echo -e "\nRestart home assistant"
exe ha core restart

echo -e "\nDone!"

echo -e "\nYou could delete folder git repository: home-assistant-eltako"
