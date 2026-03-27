document.addEventListener("DOMContentLoaded", function() {
    const menuToggle = document.querySelector(".menu-toggle");
    const navLinksWrapper = document.querySelector(".nav-links-wrapper");

    if (!menuToggle || !navLinksWrapper) {
        return;
    }

    menuToggle.addEventListener("click", function() {
        const isOpen = navLinksWrapper.classList.toggle("is-open");
        menuToggle.setAttribute("aria-expanded", String(isOpen));
    });

    window.addEventListener("resize", function() {
        if (window.innerWidth > 991.98) {
            navLinksWrapper.classList.remove("is-open");
            menuToggle.setAttribute("aria-expanded", "false");
        }
    });
});
