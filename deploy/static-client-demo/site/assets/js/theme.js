
/* Codeventra Labs: dark and light theme */

(() => {
    const root = document.documentElement;
    const themeButton = document.querySelector(".theme-toggle");
    const themeIcon = document.querySelector(".theme-icon");

    function updateThemeButton(theme) {
        if (!themeButton || !themeIcon) return;

        const isDark = theme === "dark";

        themeIcon.textContent = isDark ? "☀" : "☾";
        themeButton.setAttribute(
            "aria-label",
            isDark ? "Switch to light theme" : "Switch to dark theme"
        );
    }

    let savedTheme = "dark";

    try {
        const storedTheme = localStorage.getItem("tech-world-theme");

        if (storedTheme === "dark" || storedTheme === "light") {
            savedTheme = storedTheme;
        }
    } catch (error) {
        // The default dark theme still works if storage is unavailable.
    }

    root.dataset.theme = savedTheme;
    updateThemeButton(savedTheme);

    if (themeButton) {
        themeButton.addEventListener("click", () => {
            const nextTheme =
                root.dataset.theme === "dark" ? "light" : "dark";

            root.dataset.theme = nextTheme;
            updateThemeButton(nextTheme);

            try {
                localStorage.setItem("tech-world-theme", nextTheme);
            } catch (error) {
                // Theme switching still works for the current page.
            }
        });
    }
})();
