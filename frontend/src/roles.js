export const ROLE_INFO = {
  villager: {
    key: "villager",
    label: "Civilian",
    text: "No special power. Talk during the day and vote to catch the Mafia.",
  },
  detective: {
    key: "detective",
    label: "Police",
    text: "Each night, check one player. Learn if they are guilty or innocent.",
  },
  doctor: {
    key: "doctor",
    label: "Healer",
    text: "Each night, protect one player from the Mafia kill.",
  },
  mafia: {
    key: "mafia",
    label: "Mafia",
    text: "Each night, the Mafia team picks one player to kill together.",
  },
  godfather: {
    key: "godfather",
    label: "Godfather",
    text:
      "Secretly leads the Mafia. Has no power while other Mafia are alive. Always looks innocent to the Police. If all other Mafia die, becomes the new Mafia.",
  },
};

export function roleLabel(roleKey) {
  return ROLE_INFO[roleKey]?.label || roleKey;
}
