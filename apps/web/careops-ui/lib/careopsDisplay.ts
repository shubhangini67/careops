/** Shared display mappings for legacy labels and department fallbacks. */

export const SUPPLY_DISPLAY: Record<string, string> = {
  "Burger Buns": "Surgical Gloves",
  "Paneer": "IV Saline Bags",
  "Mozzarella": "N95 Respirators",
  "Chicken Breast": "Sterile Syringes",
  "Tomatoes": "Wound Dressings",
  "Olive Oil": "Hand Sanitizer",
  "Pizza Dough": "Oxygen Cannulas",
};

export const HOSPITAL_DEPARTMENTS = [
  "Emergency Medicine",
  "General Surgery",
  "Internal Medicine",
  "Radiology",
  "Pediatrics",
  "ICU",
  "Cardiology",
  "Orthopedics",
];

export const SAFETY_CATEGORY_LABELS: Record<string, string> = {
  "Wait Time": "ED Wait Time",
  "Care Quality": "Care Quality",
  "Stock & Availability": "Supply Availability",
  Documentation: "Documentation Accuracy",
  "Access & Value": "Access & Value",
  Environment: "Facility Environment",
};

export function toSupplyLabel(name: string): string {
  return SUPPLY_DISPLAY[name] ?? name;
}

export function toSafetyCategory(category: string): string {
  return SAFETY_CATEGORY_LABELS[category] ?? category;
}

export function departmentAtIndex(index: number, fallbackName?: string): string {
  if (fallbackName && !looksLikeMenuItem(fallbackName)) return fallbackName;
  return HOSPITAL_DEPARTMENTS[index] ?? `Department ${index + 1}`;
}

function looksLikeMenuItem(name: string): boolean {
  return /pizza|burger|paneer|cheese|tikka|mushroom|pasta|biryani|wrap|sandwich|fries|salad|soup|dessert|coffee|tea/i.test(name);
}

export function mapVolumeLabel(name: string, index: number): string {
  return looksLikeMenuItem(name) ? departmentAtIndex(index) : name;
}

export function sanitizeOpsText(text: string): string {
  let out = text;
  for (const [legacy, label] of Object.entries(SUPPLY_DISPLAY)) {
    out = out.replace(new RegExp(legacy.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), "gi"), label);
  }
  return out
    .replace(/\brestaurants?\b/gi, "hospital")
    .replace(/\bhealth score\b/gi, "operational health score")
    .replace(/\bnext service\b/gi, "next shift handoff")
    .replace(/\bcomplaint trends?\b/gi, "safety incident trends")
    .replace(/\bcustomer satisfaction\b/gi, "patient satisfaction")
    .replace(/\bingredients?\b/gi, "supply items")
    .replace(/\bmenu\b/gi, "service line")
    .replace(/\bdish(es)?\b/gi, "department$1")
    .replace(/\borders?\b/gi, "encounters")
    .replace(/\bcovers\b/gi, "visits")
    .replace(/\bkitchen\b/gi, "clinical floor");
}
