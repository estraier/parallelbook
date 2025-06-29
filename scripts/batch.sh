#! /bin/bash

if [ -z README.md ] || [ -z samples ] || [ -z books ] ; then
    echo "the current directory should be the root of the repository"
    exit
fi

function do_jsonize {
    ls samples/*-raw.txt books/*-raw.txt |
        while read file ; do
            output="${file/-raw.txt/-source.json}"
            ./scripts/jsonize_plaintext.py < "$file" > "$output"
        done
}

function do_translate {
    ls samples/*-source.json books/*-source.json |
        while read file ; do
            ./scripts/make_parallel_corpus.py "$file"
        done
}

function do_analyze {
    ls samples/*-parallel.json |
        while read file ; do
            ./scripts/analyze_parallel_corpus.py "$file"
        done
}

function do_web {
    mkdir -p web/books
    cp samples/*-parallel.json books/*-parallel.json web/books
}

function do_clean_web {
    rm -rf web/books
}

function do_build_epub {
    ls samples/*-parallel.json books/*-parallel.json |
        while read file ; do
            svgname="${file%-parallel.json}-cover.svg"
            pngname="${file%-parallel.json}-cover.png"
            ./scripts/make_cover_image.py "$svgname" --book "$file"
            rsvg-convert -b white -w 1600 -h 2250 -o "${pngname}" "${svgname}"
            ./scripts/make_parallel_epub.py "$file" --cover "${pngname}"
        done
}

function do_clean_epub {
    rm -rf samples/*-epub samples/*.epub samples/*-cover.*
    rm -rf books/*-epub books/*.epub books/*-cover.*
}

set -eux

mode="$1"
case "$mode" in
    jsonize)
        do_jsonize
        ;;
    translate)
        do_translate
        ;;
    analyze)
        do_analyze
        ;;
    web)
        do_web
        ;;
    web-clean)
        do_clean_web
        ;;
    epub)
        do_build_epub
        ;;
    epub-clean)
        do_clean_epub
        ;;
    clean)
        do_clean_web
        do_clean_epub
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
