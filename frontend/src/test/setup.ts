// Registers @testing-library/jest-dom matchers (toBeInTheDocument, toBeDisabled, …).
// This is safe to load in the node environment too — it only augments `expect`.
// @testing-library/react auto-runs cleanup after each test because vitest exposes a global
// afterEach (test.globals), so no manual cleanup wiring is needed here.
import '@testing-library/jest-dom/vitest'
