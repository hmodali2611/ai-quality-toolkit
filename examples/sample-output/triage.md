# Test failure triage

5 failing of 7 tests in the latest run.

| Category | Failures | Action |
| --- | --- | --- |
| PRODUCT_DEFECT | 2 | File a bug |
| TEST_ISSUE | 1 | Fix the test (locator, wait or data) |
| ENVIRONMENT | 1 | Re-run after infra check; notify DevOps |
| FLAKY | 1 | Quarantine and stabilize |

## Root-cause clusters

### PRODUCT_DEFECT: `expect(locator).toHaveText(expected) Expected: "$<n>" Received: "$<n>"`

Why: new failure, first seen in run-3; assertion on product behavior failed

- CheckoutTest.applyPromoCode (passed in: run-1, run-2)
- CheckoutTest.applyPromoCodeUppercase (passed in: run-1, run-2)

### ENVIRONMENT: `Error: page.goto: net::ERR_CONNECTION_REFUSED at https://media.staging.shoplite.test`

Why: new failure, first seen in run-3; infrastructure, network or device farm error

- ProfileTest.updateAvatar (passed in: run-1, run-2)

### FLAKY: `TimeoutError: locator.waitFor: Timeout <n>ms exceeded`

Why: passed and failed alternately across 3 runs; wait timed out; usually a slow page or a stale locator

- OrderHistoryTest.ordersLoad (passed in: run-2)

### TEST_ISSUE: `NoSuchElementException: An element could not be located on the page using the given search parameters (accessibility id: heart_button)`

Why: new failure, first seen in run-3; locator or element-state problem in the test

- WishlistIOSTest.addToWishlist (passed in: run-1, run-2)
