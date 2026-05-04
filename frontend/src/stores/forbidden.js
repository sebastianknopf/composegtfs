/**
 * Tracks whether the current view should show the "Access denied" screen.
 * Set by:
 *   - The router beforeEach guard (client-side permission check)
 *   - The API client's 403 handler (server-side rejection)
 * Cleared automatically when the route changes.
 */
import { ref } from 'vue'

export const forbiddenState = ref(false)
