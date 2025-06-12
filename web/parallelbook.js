"use strict";

export function renderParallelBook(
  selectorElementId, contentElementId, bookList, bookParamName, modeParamName) {
  const queryBookId = getQueryParamValue(bookParamName);
  const queryMode = getQueryParamValue(modeParamName);
  const selectorEl = document.getElementById(selectorElementId);
  if (!selectorEl) {
    console.error(`No container element: ${selectorElementId}`);
    return;
  }
  selectorEl.className = "parallel-book-navi";
  selectorEl.innerHTML = "";
  const bookSelect = document.createElement("select");
  bookSelect.id = "book-selector";
  const bookDefaultOption = document.createElement("option");
  bookDefaultOption.value = "";
  bookDefaultOption.textContent = "-- 書籍選択 --";
  bookSelect.appendChild(bookDefaultOption);
  for (const [key, [name]] of Object.entries(bookList)) {
    const option = document.createElement("option");
    option.value = key;
    option.textContent = name;
    if (key === queryBookId) {
      option.selected = true;
    }
    bookSelect.appendChild(option);
  }
  selectorEl.appendChild(bookSelect);
  const modeSelect = document.createElement("select");
  modeSelect.id = "display-mode-selector";
  const modes = [
    ["both", "英日併記"],
    ["en", "英語のみ"],
    ["ja", "日本語のみ"]
  ];
  for (const [value, label] of modes) {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = label;
    if (value === queryMode) {
      option.selected = true;
    }
    modeSelect.appendChild(option);
  }
  selectorEl.appendChild(modeSelect);
  bookSelect.addEventListener("change", () => {
    if (!bookSelect.value || bookSelect.value.length == 0) return;
    const book = bookList[bookSelect.value];
    if (!book) return;
    updateUrlParam(bookParamName, bookSelect.value);
    loadAndRenderParallelBook(contentElementId, book[1], modeSelect.value);
  });
  modeSelect.addEventListener("change", () => {
    const mode = modeSelect.value;
    const contentRoot = document.getElementById(contentElementId);
    if (!contentRoot) return;
    const parallelBlocks = contentRoot.querySelectorAll(".parallel");
    for (const block of parallelBlocks) {
      setParallelBlockMode(block, mode);
    }
    updateUrlParam(modeParamName, modeSelect.value);
  });
  if (queryBookId) {
    const book = bookList[queryBookId];
    if (book) {
      loadAndRenderParallelBook(contentElementId, book[1], queryMode);
    }
  }
}

function getQueryParamValue(paramName) {
  const params = new URLSearchParams(window.location.search);
  return params.get(paramName);
}

function updateUrlParam(paramName, paramValue) {
  const url = new URL(window.location);
  url.searchParams.set(paramName, paramValue);
  history.pushState({}, '', url);
}

async function loadAndRenderParallelBook(contentElementId, book_url, mode) {
  let response = null;
  try {
    response = await fetch(book_url);
  } catch(error) {
    console.error(`Fetch error: url=${book_url}, error=${error}`)
    return
  }
  if (!response.ok) {
    console.error(`Response error: url=${book_url}, status=${response.status}`)
    return;
  }
  let book_content = null;
  try {
    book_content = await response.json();
  } catch(error) {
    console.error(`JSON error: url=${book_url}, error=${error}`)
    return
  }
  renderParallelBookContent(contentElementId, book_content, mode);
}

function createParallelBlock(tagName, className, source, target, mode) {
  const block = document.createElement(tagName);
  block.className = `${className} parallel`;
  block.setAttribute("role", "group");
  block.setAttribute("tabindex", "0");
  const spanEn = document.createElement("span");
  spanEn.lang = "en";
  spanEn.textContent = source ?? "";
  block.appendChild(spanEn);
  const spanJa = document.createElement("span");
  spanJa.lang = "ja";
  spanJa.textContent = target ?? "";
  block.appendChild(spanJa);
  const toggle = document.createElement("span");
  toggle.lang = "zxx";
  toggle.className = "parallel-toggle";
  toggle.textContent = "▶";
  toggle.setAttribute("role", "button");
  toggle.setAttribute("aria-hidden", "true");
  toggle.addEventListener("click", (e) => {
    e.preventDefault();
    e.stopPropagation();
    const trgSpan = block.lang === "ja" ? spanEn : spanJa;
    if (trgSpan.style.display === "none") {
      trgSpan.style.display = "";
    } else {
      trgSpan.style.display = "none";
    }
  });
  block.appendChild(toggle);
  setParallelBlockMode(block, mode);
  return block;
}

function setParallelBlockMode(block, mode) {
  if (mode === "both") {
    block.lang = "zxx";
  } else {
    block.lang = mode;
  }
  const spanEn = block.querySelector('span[lang="en"]');
  const spanJa = block.querySelector('span[lang="ja"]');
  if (spanEn) {
    spanEn.style.display = (mode === "ja") ? "none" : "";
    if (mode === "ja") {
      spanEn.style.opacity = "0.8";
    } else {
      spanEn.style.opacity = "";
    }
  }
  if (spanJa) {
    spanJa.style.display = (mode === "en") ? "none" : "";
    if (mode === "ja") {
      spanJa.style.opacity = "1";
      spanJa.style.fontSize = "95%";
      spanJa.style.marginLeft = "0";
    } else {
      spanJa.style.opacity = "";
      spanJa.style.fontSize = "";
      spanJa.style.marginLeft = "0";
    }
  }
}

function renderParallelBookContent(contentElementId, book, mode) {
  const contentEl = document.getElementById(contentElementId);
  if (!contentEl) {
    console.error(`No container element: ${contentElementId}`);
    return;
  }
  contentEl.className = "parallel-book";
  contentEl.innerHTML = "";
  if (book.title) {
    contentEl.appendChild(createParallelBlock(
      "h1", "book-title", book.title.source, book.title.target, mode));
  }
  if (book.author) {
    contentEl.appendChild(createParallelBlock(
      "div", "book-author", book.author.source, book.author.target, mode));
  }
  for (const chapter of book.chapters ?? []) {
    const chapterSection = document.createElement("section");
    if (chapter.title) {
      chapterSection.appendChild(createParallelBlock(
        "h2", "chapter-title", chapter.title.source, chapter.title.target, mode));
    }
    for (const block of chapter.body ?? []) {
      if (block.paragraph) {
        const pane = document.createElement("p");
        pane.className = "paragraph"
        for (const item of block.paragraph) {
          pane.appendChild(createParallelBlock(
            "div", "sentence", item.source, item.target, mode));
        }
        chapterSection.appendChild(pane);
      } else if (block.header) {
        for (const item of block.header) {
          chapterSection.appendChild(createParallelBlock(
            "h3", "header", item.source, item.target, mode));
        }
      } else if (block.list) {
        const ul = document.createElement("ul");
        ul.className = "list"
        for (const item of block.list) {
          const li = document.createElement("li");
          li.appendChild(createParallelBlock(
            "div", "list-item", item.source, item.target, mode));
          ul.appendChild(li);
        }
        chapterSection.appendChild(ul);
      } else if (block.table) {
        const table = document.createElement("table");
        table.className = "table"
        for (const row of block.table) {
          const tr = document.createElement("tr");
          for (const cell of row) {
            const td = document.createElement("td");
            td.appendChild(createParallelBlock(
              "div", "table-cell", cell.source, cell.target, mode));
            tr.appendChild(td);
          }
          table.appendChild(tr);
        }
        chapterSection.appendChild(table);
      } else if (block.macro?.name === "image") {
        const values = (block.macro.value ?? "").trim().split(" ");
        const pane = document.createElement("div");
        pane.className = "macro-image"
        const img = document.createElement("img");
        img.src = values[0];
        if (values.length > 0) {
          img.alt = values.slice(1).join(" ");
        }
        pane.appendChild(img);
        chapterSection.appendChild(pane);
      }
    }
    contentEl.appendChild(chapterSection);
  }
}
