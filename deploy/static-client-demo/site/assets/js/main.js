
/* Codeventra Labs: small shared page enhancements */

(() => {
    const yearElement = document.querySelector("#current-year");

    if (yearElement) {
        yearElement.textContent = new Date().getFullYear();
    }
})();
