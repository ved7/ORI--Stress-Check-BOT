export const CHECK_IN_STEPS = [
  {
    buttonLabel: "Send to Ori",
    description: "Start by naming what feels most true emotionally, even if it is messy or mixed.",
    helper: "Name the feeling closest to the surface. One or two sentences is enough.",
    number: 1,
    placeholder: "I'm feeling tense, low, restless, or ...",
    shortTitle: "Feelings",
    starters: [
      "I feel stretched thin and a little wired.",
      "I feel heavy and mentally crowded.",
      "I feel okay on the outside, but tense underneath.",
    ],
    title: "Emotional check-in",
  },
  {
    buttonLabel: "Send to Ori",
    description: "Zoom in on the main thing pulling at your attention instead of listing everything.",
    helper: "Focus on the biggest source of pressure instead of the whole list.",
    number: 2,
    placeholder: "The main thing weighing on me is ...",
    shortTitle: "Stressor",
    starters: [
      "The biggest pressure right now is work uncertainty.",
      "I'm carrying too many responsibilities at once.",
      "One relationship is taking up a lot of emotional space.",
    ],
    title: "Stressor identification",
  },
  {
    buttonLabel: "Send to Ori",
    description: "Notice how stress is landing physically so Ori can reflect the full picture back.",
    helper: "Notice what stress is doing in your body, energy, or sleep.",
    number: 3,
    placeholder: "I'm noticing it in my shoulders, sleep, energy, or ...",
    shortTitle: "Body",
    starters: [
      "My chest feels tight and my sleep has been uneven.",
      "I feel tired but still can't fully relax.",
      "My jaw and shoulders stay tense most of the day.",
    ],
    title: "Body scan",
  },
  {
    buttonLabel: "Send to Ori",
    description: "There is no right answer here. Share the coping pattern you actually fall back on.",
    helper: "Share what you usually do when stress picks up, even if it is imperfect.",
    number: 4,
    placeholder: "When stress builds, I usually ...",
    shortTitle: "Coping",
    starters: [
      "I keep pushing and avoid slowing down.",
      "I withdraw and try to deal with it alone.",
      "I distract myself before I can fully process it.",
    ],
    title: "Coping patterns",
  },
  {
    buttonLabel: "Create my profile",
    description: "End by saying what kind of support would actually feel useful right now.",
    helper: "Say what kind of support would feel useful right now.",
    number: 5,
    placeholder: "What would help most right now is ...",
    shortTitle: "Support",
    starters: [
      "I need a calmer plan and a sense of direction.",
      "I need reassurance and someone to help me slow down.",
      "I need practical support and clearer priorities.",
    ],
    title: "Support preference",
  },
];


export function getStepContent(step) {
  const safeStep = Math.min(Math.max(step, 1), CHECK_IN_STEPS.length);
  return CHECK_IN_STEPS[safeStep - 1];
}
