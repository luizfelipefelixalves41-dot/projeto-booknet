"use strict";

const sections = [...document.querySelectorAll("main > section[id]")];
const navigationLinks = [...document.querySelectorAll(".nav-link")];
const topLink = document.querySelector(".back-to-top");
let updatePending = false;

function updateNavigation() {
  const offset = parseFloat(getComputedStyle(document.documentElement).scrollPaddingTop) || 100;
  const readingLine = Math.max(offset + 24, window.innerHeight * 0.25);
  let activeId = sections[0].id;

  for (const section of sections) {
    if (section.getBoundingClientRect().top <= readingLine) activeId = section.id;
  }

  // The last section may be too short to reach the navigation threshold.
  const atBottom = window.scrollY + window.innerHeight >= document.documentElement.scrollHeight - 8;
  if (atBottom && window.scrollY > 0) activeId = sections[sections.length - 1].id;

  for (const link of navigationLinks) {
    const isActive = link.hash === `#${activeId}`;
    const newlyActive = isActive && !link.classList.contains("is-active");
    link.classList.toggle("is-active", isActive);
    if (isActive) link.setAttribute("aria-current", "location");
    else link.removeAttribute("aria-current");

    // Keep the current item visible in the mobile navigation without moving the page.
    const navigation = link.parentElement;
    if (newlyActive && navigation.scrollWidth > navigation.clientWidth) {
      const item = link.getBoundingClientRect();
      const bar = navigation.getBoundingClientRect();
      if (item.left < bar.left || item.right > bar.right) {
        navigation.scrollLeft += item.left + item.width / 2 - bar.left - bar.width / 2;
      }
    }
  }

  topLink.hidden = window.scrollY < 400;
  updatePending = false;
}

function scheduleNavigationUpdate() {
  if (updatePending) return;
  updatePending = true;
  window.requestAnimationFrame(updateNavigation);
}

window.addEventListener("scroll", scheduleNavigationUpdate, { passive: true });
window.addEventListener("resize", scheduleNavigationUpdate);
window.addEventListener("pageshow", scheduleNavigationUpdate);
updateNavigation();

// Content stays visible even when JavaScript or IntersectionObserver is unavailable.
if ("IntersectionObserver" in window && !window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
  const entryObserver = new IntersectionObserver((entries, observer) => {
    for (const entry of entries) {
      if (!entry.isIntersecting) continue;
      entry.target.classList.add("is-visible");
      observer.unobserve(entry.target);
    }
  }, { threshold: 0.08 });

  document.querySelectorAll(".reveal").forEach(element => entryObserver.observe(element));
}
