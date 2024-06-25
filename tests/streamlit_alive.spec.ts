// Keep streamlit active for Travelstruck passport reader

import { test, expect } from '@playwright/test';

test('has title', async ({ page }) => {
  await page.goto('https://travelstruck.streamlit.app/')
});
