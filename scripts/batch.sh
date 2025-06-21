#! /bin/bash

if [ -z README.md ] || [ -z samples ] || [ -z books ] ; then
    echo "the current directory should be the root of the repository"
    exit
fi

function jsonize {
    ls samples/*-raw.txt books/*-raw.txt |
        while read file ; do
            output="${file/-raw.txt/-source.json}"
            ./scripts/jsonize_plaintext.py < "$file" > "$output"
        done
}

function translate {
    ls samples/*-source.json books/*-source.json |
        while read file ; do
            ./scripts/make_parallel_book_chatgpt.py "$file"
        done
}

function web {
    mkdir -p web/books
    cp samples/*-parallel.json books/*-parallel.json web/books
}

function clean_web {
    rm -rf web/books
}

function build_epub {
    ls samples/*-parallel.json books/*-parallel.json |
        while read file ; do
            svgname="${file%-parallel.json}-cover.svg"
            pngname="${file%-parallel.json}-cover.png"
            ./scripts/make_cover_image.py "$svgname" --book "$file"
            rsvg-convert -b white -w 1600 -h 2250 -o "${pngname}" "${svgname}"
            ./scripts/make_parallel_epub.py "$file" --cover "${pngname}"
        done
}

function clean_epub {
    rm -rf samples/*-epub samples/*.epub samples/*-cover.*
    rm -rf books/*-epub books/*.epub books/*-cover.*
}

set -eux

mode="$1"
case "$mode" in
    jsonize)
        jsonize
        ;;
    translate)
        translate
        ;;
    web)
        web
        ;;
    web-clean)
        clean_web
        ;;
    epub)
        build_epub
        ;;
    epub-clean)
        clean_epub
        ;;
    clean)
        clean_web
        clean_epub
        ;;
    "")
        echo "specify a mode"
        exit 1
        ;;
    *)
        echo "unknown mode $mode"
        exit 1
        ;;
esac
