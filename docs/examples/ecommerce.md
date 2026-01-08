# E-Commerce Epic Example

A complete example of an e-commerce epic with multiple user stories.

## Full Example

```markdown
# 🛒 E-Commerce Platform Epic

> **Epic: Build modern e-commerce platform MVP**

---

## Epic Summary

| Field | Value |
|-------|-------|
| **Epic Name** | E-Commerce Platform MVP |
| **Status** | 🔄 In Progress |
| **Priority** | 🔴 Critical |
| **Start Date** | January 2025 |
| **Target Release** | v1.0.0 |

### Summary

Build a modern e-commerce platform with product catalog, shopping cart, 
checkout, and order management capabilities.

### Description

This epic covers the core functionality needed to launch an MVP e-commerce platform.

**Key Areas:**
- **Product Management**: Catalog, search, filtering
- **Shopping Experience**: Cart, wishlist, checkout
- **Order Processing**: Payment, fulfillment, tracking
- **User Accounts**: Registration, authentication, profiles

### Business Value

- **Revenue Generation**: Enable online sales channel
- **Customer Reach**: Expand market beyond physical locations
- **Operational Efficiency**: Automated order processing
- **Data Insights**: Customer behavior analytics

---

## User Stories

---

### 🚀 US-001: Product Catalog Display

| Field | Value |
|-------|-------|
| **Story Points** | 5 |
| **Priority** | 🔴 Critical |
| **Status** | ✅ Done |

#### Description

**As a** customer browsing the store
**I want** to view products in a catalog
**So that** I can find items I want to purchase

The catalog should support grid and list views, with filtering and sorting options.

#### Acceptance Criteria

- [x] Products display with image, name, price
- [x] Grid and list view toggle works
- [x] Category filtering is functional
- [x] Price sorting (low-high, high-low) works
- [x] Pagination loads more products

#### Subtasks

| # | Subtask | Description | SP | Status |
|---|---------|-------------|:--:|--------|
| 1 | Create product card component | Build reusable card with image, title, price | 1 | ✅ Done |
| 2 | Implement grid/list toggle | Add view switcher with state persistence | 1 | ✅ Done |
| 3 | Add category filters | Create filter sidebar with category checkboxes | 1 | ✅ Done |
| 4 | Implement sorting | Add sort dropdown with price/name options | 1 | ✅ Done |
| 5 | Add pagination | Implement infinite scroll or page numbers | 1 | ✅ Done |

#### Related Commits

| Commit | Message |
|--------|---------|
| `a1b2c3d` | feat: add product card component |
| `e4f5g6h` | feat: implement catalog grid view |
| `i7j8k9l` | feat: add filtering and sorting |

---

### 🛒 US-002: Shopping Cart Management

| Field | Value |
|-------|-------|
| **Story Points** | 8 |
| **Priority** | 🔴 Critical |
| **Status** | 🔄 In Progress |

#### Description

**As a** customer shopping on the site
**I want** to add items to my cart and manage quantities
**So that** I can collect items before checkout

#### Acceptance Criteria

- [x] Add to cart button on product pages
- [x] Cart icon shows item count
- [ ] Cart drawer shows all items
- [ ] Quantity can be increased/decreased
- [ ] Items can be removed from cart
- [ ] Cart persists across sessions

#### Subtasks

| # | Subtask | Description | SP | Status |
|---|---------|-------------|:--:|--------|
| 1 | Create cart context | Implement React context for cart state | 2 | ✅ Done |
| 2 | Build add to cart flow | Add button, animation, notification | 2 | ✅ Done |
| 3 | Create cart drawer | Slide-out cart with item list | 2 | 🔄 In Progress |
| 4 | Add quantity controls | Plus/minus buttons with stock validation | 1 | 📋 Planned |
| 5 | Implement persistence | Save cart to localStorage/API | 1 | 📋 Planned |

---

### 💳 US-003: Checkout Flow

| Field | Value |
|-------|-------|
| **Story Points** | 13 |
| **Priority** | 🔴 Critical |
| **Status** | 📋 Planned |

#### Description

**As a** customer ready to purchase
**I want** to complete checkout with my payment details
**So that** I can place my order

#### Acceptance Criteria

- [ ] Multi-step checkout wizard
- [ ] Shipping address form with validation
- [ ] Payment method selection
- [ ] Stripe integration for payments
- [ ] Order summary with totals
- [ ] Order confirmation page

#### Subtasks

| # | Subtask | Description | SP | Status |
|---|---------|-------------|:--:|--------|
| 1 | Create checkout wizard | Multi-step form with progress indicator | 2 | 📋 Planned |
| 2 | Build address form | Shipping/billing forms with validation | 2 | 📋 Planned |
| 3 | Add shipping options | Carrier selection with rate calculation | 2 | 📋 Planned |
| 4 | Integrate Stripe | Payment form with Stripe Elements | 3 | 📋 Planned |
| 5 | Create order summary | Itemized summary with taxes and totals | 2 | 📋 Planned |
| 6 | Build confirmation page | Order success with details and next steps | 2 | 📋 Planned |

---

### 🔒 US-004: User Authentication

| Field | Value |
|-------|-------|
| **Story Points** | 5 |
| **Priority** | 🟡 High |
| **Status** | ✅ Done |

#### Description

**As a** returning customer
**I want** to create an account and log in
**So that** I can save my information and view order history

#### Acceptance Criteria

- [x] Registration form with email verification
- [x] Login form with remember me option
- [x] Password reset flow
- [x] OAuth login (Google, Apple)
- [x] Session management

#### Subtasks

| # | Subtask | Description | SP | Status |
|---|---------|-------------|:--:|--------|
| 1 | Create auth forms | Login and registration UI components | 1 | ✅ Done |
| 2 | Implement JWT auth | Token-based authentication flow | 2 | ✅ Done |
| 3 | Add OAuth providers | Google and Apple sign-in integration | 1 | ✅ Done |
| 4 | Build password reset | Email-based password recovery | 1 | ✅ Done |

#### Related Commits

| Commit | Message |
|--------|---------|
| `m1n2o3p` | feat: implement authentication system |
| `q4r5s6t` | feat: add OAuth providers |

---

### 📊 US-005: Order History Dashboard

| Field | Value |
|-------|-------|
| **Story Points** | 3 |
| **Priority** | 🟢 Medium |
| **Status** | 📋 Planned |

#### Description

**As a** registered customer
**I want** to view my past orders
**So that** I can track deliveries and reorder items

#### Acceptance Criteria

- [ ] List of all past orders
- [ ] Order detail view with items
- [ ] Order status tracking
- [ ] Reorder button for past orders

#### Subtasks

| # | Subtask | Description | SP | Status |
|---|---------|-------------|:--:|--------|
| 1 | Create orders list | Paginated list with status badges | 1 | 📋 Planned |
| 2 | Build order detail view | Full order info with line items | 1 | 📋 Planned |
| 3 | Add reorder functionality | Copy items to cart with availability check | 1 | 📋 Planned |

---
```

## Sync This Epic

```bash
# Preview changes
spectryn --markdown ecommerce-epic.md --epic SHOP-100

# Execute sync
spectryn --markdown ecommerce-epic.md --epic SHOP-100 --execute
```

## Expected Results in Jira

After sync, you'll see:

- **5 stories** linked to epic SHOP-100
- **17 subtasks** across all stories
- Descriptions formatted with As a/I want/So that
- Status badges matching the emoji indicators
- Acceptance criteria as checklists

