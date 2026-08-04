// Guest Concierge (Phase 6A-34) -- types for the /concierge consumer chat.
// Mirrors apps/api/app/domain/services/concierge_service.py's tool return
// shapes and ConciergeSession fields exactly -- see that file before
// changing any of these.

export interface ConciergeVenue {
  restaurant_id: string;
  name?: string;
  avg_rating?: number;
  cost_for_two?: number;
  estimated_cost?: number;
  distance_km?: number;
  cuisines?: string[];
  amenities?: string[];
  deals?: { title?: string; isFree?: boolean }[];
}

export interface ConciergeSlot {
  display_time?: string;
  reservation_time?: number;
  availability_count?: number;
  slot_id?: number;
  item_id?: string;
  deal_title?: string;
}

export interface ConciergeSupplyItem {
  query?: string;
  name?: string;
  spin_id: string;
  price?: number;
  unit?: string;
  in_stock?: boolean;
}

export interface ConciergeBooking {
  restaurant_id?: string;
  restaurant_name?: string;
  display_time?: string;
  reservation_time?: number;
  headcount?: number;
  estimated_cost?: number;
  status?: string;
  order_id?: string;
  confirmation_code?: string;
}

export interface ConciergeOrder {
  order_id?: string;
  status?: string;
  estimated_delivery?: string;
  estimated_delivery_mins?: string;
  total?: number;
  items?: unknown[];
}

export interface ConciergeSessionState {
  session_id: string;
  occasion: string | null;
  headcount: number | null;
  budget_inr: number | null;
  budget_spent: number;
  budget_remaining: number | null;
  preferences: string[];
  active_bookings: ConciergeBooking[];
  active_food_orders: ConciergeOrder[];
  active_instamart_orders: ConciergeOrder[];
  suggested_venues: ConciergeVenue[];
  instamart_cart: ConciergeSupplyItem[];
}

export interface ConciergeHealth {
  swiggy_connected: boolean;
  staging_enabled: boolean;
  tools_available: string[];
  tools_pending_staging: string[];
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export interface ConciergeToolResult { tool: string; data: any }

export interface ConciergeMessage {
  role: "user" | "assistant";
  text: string;
  toolResults: ConciergeToolResult[];
  streaming?: boolean;
  statusText?: string;
}
