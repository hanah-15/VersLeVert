const test = require("node:test");
const assert = require("node:assert/strict");
const vm = require("node:vm");
const fs = require("node:fs");
const path = require("node:path");
const source = fs.readFileSync(path.join(__dirname, "static/places/places.js"), "utf8");

function element(value = "") {
  return {value, hidden: false, disabled: false, textContent: "", dataset: {}, handlers: {},
    addEventListener(type, callback) { this.handlers[type] = callback; },
    focus() {},
    fire(type) { return this.handlers[type]?.(); },
  };
}
function run({form, proximity, fetch, navigator = {}}) {
  vm.runInNewContext(source, {
    document: {
      querySelectorAll: () => proximity ? [proximity] : [],
      querySelector: selector => selector === "[data-recommendation-form]" ? form || null : null,
    },
    window: {fetch}, fetch, navigator, AbortController, FormData, setTimeout, clearTimeout,
  });
}
function response(data) {
  return {ok: true, redirected: false, headers: {get: () => "application/json"}, json: async () => data};
}
function deferred() {
  let resolve;
  const promise = new Promise(done => { resolve = done; });
  return {promise, resolve};
}
function areaForm() {
  const nodes = Object.fromEntries(["area-controls", "use-location", "location-status", "location-selection", "location-name", "location-accuracy", "clear-location"].map(key => [key, element()]));
  nodes["area-controls"].dataset = {locationEndpoint: "/places/position/quartier/", csrfToken: "test"};
  nodes["location-selection"].hidden = true;
  let submissions = 0;
  return {
    nodes, elements: Object.fromEntries(["latitude", "longitude", "location_token", "near_place", "city", "radius"].map(key => [key, element()])),
    querySelector(selector) { return nodes[selector.slice(6, -1)]; },
    requestSubmit() { submissions++; }, get submissions() { return submissions; },
  };
}

test("GPS names the area and waits for the chosen distance before searching", async () => {
  const form = areaForm();
  const lookup = deferred();
  let locate;
  run({proximity: form, fetch: () => lookup.promise, navigator: {geolocation: {getCurrentPosition(success) { locate = success; }}}});
  form.nodes["use-location"].fire("click");
  const pending = locate({coords: {latitude: 36.742946, longitude: 10.250764, accuracy: 40}});
  assert.equal(form.nodes["location-selection"].hidden, false);
  assert.equal(form.elements.radius.value, "10");
  form.elements.radius.value = "25";
  lookup.resolve(response({label: "Nouvelle Médina", location_token: "signed"}));
  await pending;
  assert.equal(form.nodes["location-name"].textContent, "Nouvelle Médina");
  assert.equal(form.elements.radius.value, "25");
  assert.equal(form.elements.location_token.value, "signed");
  assert.equal(form.submissions, 0);
  assert.equal(form.nodes["use-location"].disabled, false);
});

test("a delayed GPS label cannot replace a newly typed city", async () => {
  const form = areaForm();
  const lookup = deferred();
  let locate;
  run({proximity: form, fetch: () => lookup.promise, navigator: {geolocation: {getCurrentPosition(success) { locate = success; }}}});
  form.nodes["use-location"].fire("click");
  const pending = locate({coords: {latitude: 36.74, longitude: 10.25, accuracy: 500}});
  form.elements.city.value = "La Marsa";
  form.elements.city.fire("input");
  lookup.resolve(response({label: "Old area", location_token: "old"}));
  await pending;
  assert.equal(form.elements.city.value, "La Marsa");
  assert.equal(form.elements.latitude.value, "");
  assert.equal(form.elements.location_token.value, "");
  assert.equal(form.nodes["location-selection"].hidden, true);
});

test("GPS permission denial leaves the city search available", () => {
  const form = areaForm();
  form.elements.city.value = "Nouvelle Médina";
  let denied;
  run({proximity: form, fetch: () => { throw Error("No request expected"); }, navigator: {geolocation: {getCurrentPosition(success, failure) { denied = failure; }}}});
  form.nodes["use-location"].fire("click");
  denied();
  assert.equal(form.elements.city.value, "Nouvelle Médina");
  assert.equal(form.nodes["use-location"].disabled, false);
  assert.match(form.nodes["location-status"].textContent, /indisponible/);
});

function reviewForm() {
  const nodes = Object.fromEntries(["prepare-recommendation", "apply-preparation", "restore-preparation", "dismiss-preparation", "preparation-status", "preparation-errors", "preparation-result", "prepared-description", "preparation-warnings", "prepared-location-section", "prepared-location", "prepared-location-note"].map(key => [key, element()]));
  return {
    nodes, dataset: {preparationEndpoint: "/places/recommandations/preparer/"},
    elements: {product_name: element("Savon"), category: element("personal_care"), description: element("Cheap, smells good and worth buying. Bought at Monoprix."),
      purchase_location: element(), place: element(), csrfmiddlewaretoken: element("csrf")},
    querySelector(selector) { return nodes[selector.slice(6, -1)]; },
  };
}
const suggestion = {description: "Je trouve ce savon abordable et son parfum agréable. Cet achat en vaut la peine.", product_name: "Savon", category: "personal_care", purchase_location: "Monoprix", warnings: []};

test("accepting a suggestion fills an empty shop and undo restores both fields", async () => {
  const form = reviewForm();
  const original = form.elements.description.value;
  run({form, fetch: async () => response(suggestion)});
  await form.nodes["prepare-recommendation"].fire("click");
  assert.equal(form.elements.description.value, original);
  assert.equal(form.elements.purchase_location.value, "");
  assert.equal(form.nodes["prepared-location"].textContent, "Monoprix");
  form.nodes["apply-preparation"].fire("click");
  assert.equal(form.elements.description.value, suggestion.description);
  assert.equal(form.elements.purchase_location.value, "Monoprix");
  form.nodes["restore-preparation"].fire("click");
  assert.equal(form.elements.description.value, original);
  assert.equal(form.elements.purchase_location.value, "");
});

test("manual shop changes made during preparation survive acceptance and undo", async () => {
  const form = reviewForm();
  const request = deferred();
  run({form, fetch: () => request.promise});
  const pending = form.nodes["prepare-recommendation"].fire("click");
  form.elements.purchase_location.value = "Ma boutique habituelle";
  form.elements.purchase_location.fire("input");
  request.resolve(response(suggestion));
  await pending;
  form.nodes["apply-preparation"].fire("click");
  assert.equal(form.elements.purchase_location.value, "Ma boutique habituelle");
  form.nodes["restore-preparation"].fire("click");
  assert.equal(form.elements.purchase_location.value, "Ma boutique habituelle");
});

test("late AI responses and undo cannot overwrite newer review edits", async () => {
  const form = reviewForm();
  const request = deferred();
  run({form, fetch: () => request.promise});
  const pending = form.nodes["prepare-recommendation"].fire("click");
  form.elements.description.value = "My new review";
  request.resolve(response(suggestion));
  await pending;
  assert.equal(form.nodes["preparation-result"].hidden, true);
  assert.equal(form.elements.description.value, "My new review");
  // A second accepted suggestion may still be edited before undo.
  form.elements.description.value = "Another long review for preparing.";
  await form.nodes["prepare-recommendation"].fire("click");
  form.nodes["apply-preparation"].fire("click");
  form.elements.description.value = "My final text";
  form.nodes["restore-preparation"].fire("click");
  assert.equal(form.elements.description.value, "My final text");
});
