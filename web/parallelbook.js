"use strict";

export function renderParallelBook(selectorElementId, contentElementId, bookList, bookParamName) {
  const selectorEl = document.getElementById(selectorElementId);
  if (!selectorEl) {
    console.error(`No container element: ${selectorElementId}`);
    return;
  }
  selectorEl.className = "parallel-book-navi";
  selectorEl.innerHTML = "";
  const label = document.createElement("label");
  label.textContent = "書籍選択：";
  label.setAttribute("for", "book-selector");
  const select = document.createElement("select");
  select.id = "book-selector";
  const defaultOption = document.createElement("option");
  defaultOption.value = "";
  defaultOption.textContent = "-- 選択 --";
  select.appendChild(defaultOption);
  const currentBookId = getBookIdFromQuery(bookParamName);
  for (const [key, [name]] of Object.entries(bookList)) {
    const option = document.createElement("option");
    option.value = key;
    option.textContent = name;
    if (key === currentBookId) {
      option.selected = true;
    }
    select.appendChild(option);
  }
  select.addEventListener("change", () => {
    const selected = select.value;
    const url = new URL(window.location.href);
    if (selected) {
      url.searchParams.set(bookParamName, selected);
    } else {
      url.searchParams.delete(bookParamName);
    }
    window.location.href = url.toString();
  });
  selectorEl.appendChild(label);
  selectorEl.appendChild(select);
  if (currentBookId) {
    const book = bookList[currentBookId];
    if (book) {
      loadAndRenderParallelBook(contentElementId, book[1]);
    }
  }
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
    modeSelect.appendChild(option);
  }
  modeSelect.addEventListener("change", () => {
    const mode = modeSelect.value;
    const contentRoot = document.getElementById(contentElementId);
    if (!contentRoot) return;
    const parallelBlocks = contentRoot.querySelectorAll(".parallel");
    for (const block of parallelBlocks) {
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
          spanJa.style.fontSize = "100%";
          spanJa.style.marginLeft = "0";
        } else {
          spanJa.style.opacity = "";
          spanJa.style.fontSize = "";
          spanJa.style.marginLeft = "0";
        }
      }
    }
  });
  selectorEl.appendChild(modeSelect);
}

function getBookIdFromQuery(bookParamName) {
  const params = new URLSearchParams(window.location.search);
  return params.get(bookParamName);
}

async function loadAndRenderParallelBook(contentElementId, book_url) {
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
  renderParallelBookContent(contentElementId, book_content);
}


function renderParallelBookContent(contentElementId, book) {
  const contentEl = document.getElementById(contentElementId);
  if (!contentEl) {
    console.error(`No container element: ${contentElementId}`);
    return;
  }
  contentEl.className = "parallel-book";
  contentEl.innerHTML = "";
  function createParallelBlock(tagName, className, source, target) {
    const container = document.createElement(tagName);
    container.className = `${className} parallel`;
    const spanEn = document.createElement("span");
    spanEn.lang = "en";
    spanEn.textContent = source ?? "";
    container.appendChild(spanEn);
    const spanJa = document.createElement("span");
    spanJa.lang = "ja";
    spanJa.textContent = target ?? "";
    container.appendChild(spanJa);
    const toggle = document.createElement("span");
    toggle.lang = "zxx";
    toggle.className = "parallel-toggle";
    toggle.textContent = "▶";
    toggle.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      const trgSpan = container.lang === "ja" ? spanEn : spanJa;
      if (trgSpan.style.display === "none") {
        trgSpan.style.display = "";
      } else {
        trgSpan.style.display = "none";
      }
    });
    container.appendChild(toggle);
    return container;
  }
  if (book.title) {
    contentEl.appendChild(createParallelBlock(
      "h1", "book-title", book.title.source, book.title.target));
  }
  if (book.author) {
    contentEl.appendChild(createParallelBlock(
      "div", "book-author", book.author.source, book.author.target));
  }
  for (const chapter of book.chapters ?? []) {
    const chapterSection = document.createElement("section");
    if (chapter.title) {
      chapterSection.appendChild(createParallelBlock(
        "h2", "chapter-title", chapter.title.source, chapter.title.target));
    }
    for (const block of chapter.body ?? []) {
      if (block.paragraph) {
        const pane = document.createElement("p");
        pane.className = "paragraph"
        for (const item of block.paragraph) {
          pane.appendChild(createParallelBlock("div", "sentence", item.source, item.target));
        }
        chapterSection.appendChild(pane);
      } else if (block.header) {
        for (const item of block.header) {
          chapterSection.appendChild(createParallelBlock(
            "h3", "header", item.source, item.target));
        }
      } else if (block.list) {
        const ul = document.createElement("ul");
        ul.className = "list"
        for (const item of block.list) {
          const li = document.createElement("li");
          li.appendChild(createParallelBlock("div", "list-item", item.source, item.target));
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
            td.appendChild(createParallelBlock("div", "table-cell", cell.source, cell.target));
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
