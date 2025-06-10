"use strict";

export function renderParallelBook(selectorElementId, contentElementId, bookList, bookParamName) {
  const selectorEl = document.getElementById(selectorElementId);
  if (!selectorEl) {
    console.error(`No container element: ${selectorElementId}`);
    return;
  }
  const label = document.createElement("label");
  label.textContent = "読みたい書籍を選択してください：";
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
  contentEl.innerHTML = "";
  function createParallelBlock(tagName, classPrefix, source, target) {
    const container = document.createElement(tagName);
    const spanEn = document.createElement("span");
    spanEn.className = `${classPrefix}-en parallel`;
    spanEn.lang = "en";
    spanEn.textContent = source ?? "";
    const spanJa = document.createElement("span");
    spanJa.className = `${classPrefix}-ja parallel`;
    spanJa.lang = "ja";
    spanJa.textContent = target ?? "";
    container.appendChild(spanEn);
    container.appendChild(spanJa);
    return container;
  }
  if (book.title) {
    contentEl.appendChild(createParallelBlock("h1", "book-title", book.title.source, book.title.target));
  }
  if (book.author) {
    contentEl.appendChild(createParallelBlock("p", "book-author", book.author.source, book.author.target));
  }
  for (const chapter of book.chapters ?? []) {
    const chapterSection = document.createElement("section");
    if (chapter.title) {
      chapterSection.appendChild(createParallelBlock("h2", "chapter-title", chapter.title.source, chapter.title.target));
    }
    for (const block of chapter.body ?? []) {
      if (block.paragraph) {
        for (const item of block.paragraph) {
          chapterSection.appendChild(createParallelBlock("div", "paragraph", item.source, item.target));
        }
      } else if (block.header) {
        for (const item of block.header) {
          chapterSection.appendChild(createParallelBlock("h3", "header", item.source, item.target));
        }
      } else if (block.list) {
        const ul = document.createElement("ul");
        for (const item of block.list) {
          const li = document.createElement("li");
          li.appendChild(createParallelBlock("div", "list-item", item.source, item.target));
          ul.appendChild(li);
        }
        chapterSection.appendChild(ul);
      } else if (block.table) {
        const table = document.createElement("table");
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
        const img = document.createElement("img");
        img.src = block.macro.value;
        img.alt = "";
        img.className = "macro-image";
        chapterSection.appendChild(img);
      }
    }
    contentEl.appendChild(chapterSection);
  }
}
