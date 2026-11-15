// Yes-or-no choices the start screen remembers in this browser, such as
// "Hide these steps". Only the names in FLAGS can be stored, and only the
// text "1" under them, so nothing about a tablet or a dashboard can end up
// in the browser's storage through here. A browser that refuses storage
// remembers nothing; the panel works the same.

const PREFIX = "apollo_tab.";

// Every flag there is.
export const FLAGS = ["guide_hidden"];

function keyOf(name) {
  return FLAGS.includes(name) ? PREFIX + name : null;
}

// Whether the flag is set.
export function flag(name) {
  const key = keyOf(name);
  if (!key) {
    return false;
  }
  try {
    return window.localStorage.getItem(key) === "1";
  } catch {
    return false;
  }
}

// Sets the flag. Returns whether the browser kept it.
export function setFlag(name) {
  const key = keyOf(name);
  if (!key) {
    return false;
  }
  try {
    window.localStorage.setItem(key, "1");
    return true;
  } catch {
    return false;
  }
}
