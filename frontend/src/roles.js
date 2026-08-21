export const ROLE_INFO = {
  civilian: {
    key: "civilian",
    label: "Civilian",
    text: "No special power. Talk during the day and vote at the table.",
  },
  inspector: {
    key: "inspector",
    label: "Inspector",
    text: "Each night, investigate one player. Learn whether they read as Table or Hand.",
  },
  watchman: {
    key: "watchman",
    label: "Watchman",
    text: "Each night, protect one player from the Hand's target. Cannot protect the same player two nights running.",
  },
  hand: {
    key: "hand",
    label: "Hand",
    text:
      "Each night, the Black Hand chooses together: kill a player, or offer one Table player a place in the Hand.",
  },
};

export function roleLabel(roleKey) {
  return ROLE_INFO[roleKey]?.label || roleKey;
}
