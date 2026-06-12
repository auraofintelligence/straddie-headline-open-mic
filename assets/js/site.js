(function () {
  const body = document.body;
  const currentPage = body.dataset.page || "home";

  document.querySelectorAll("[data-nav]").forEach((link) => {
    if (link.dataset.nav === currentPage) {
      link.setAttribute("aria-current", "page");
    }
  });

  const topButton = document.querySelector(".to-top");
  if (topButton) {
    const toggleTopButton = () => {
      topButton.classList.toggle("is-visible", window.scrollY > 520);
    };

    topButton.addEventListener("click", () => {
      window.scrollTo({ top: 0, behavior: "smooth" });
    });

    window.addEventListener("scroll", toggleTopButton, { passive: true });
    toggleTopButton();
  }

  const searchInput = document.querySelector("#headline-search");
  const sourceSelect = document.querySelector("#source-filter");
  const cards = Array.from(document.querySelectorAll("[data-headline-card]"));
  const count = document.querySelector("#headline-count");

  if (cards.length && (searchInput || sourceSelect)) {
    const updateCards = () => {
      const query = (searchInput ? searchInput.value : "").trim().toLowerCase();
      const source = sourceSelect ? sourceSelect.value : "all";
      let visible = 0;

      cards.forEach((card) => {
        const matchesQuery = !query || card.dataset.search.includes(query);
        const matchesSource = source === "all" || card.dataset.source === source;
        const show = matchesQuery && matchesSource;
        card.classList.toggle("is-hidden", !show);
        if (show) {
          visible += 1;
        }
      });

      if (count) {
        count.textContent = String(visible);
      }
    };

    if (searchInput) {
      searchInput.addEventListener("input", updateCards);
    }
    if (sourceSelect) {
      sourceSelect.addEventListener("change", updateCards);
    }
    updateCards();
  }
})();
