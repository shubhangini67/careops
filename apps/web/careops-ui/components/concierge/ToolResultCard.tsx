"use client";

import { ConciergeSlot, ConciergeSupplyItem, ConciergeVenue } from "@/types/concierge";
import VenueCard from "@/components/concierge/VenueCard";
import SlotCard from "@/components/concierge/SlotCard";
import ProductCard from "@/components/concierge/ProductCard";
import OrderConfirmation from "@/components/concierge/OrderConfirmation";
import { BudgetSummaryCard, ErrorNote } from "@/components/concierge/BudgetWarning";
import { MenuCard, RestaurantCard } from "@/components/concierge/FoodCards";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Data = Record<string, any>;

export default function ToolResultCard({
  tool,
  data,
  headcount,
  onQuickMessage,
}: {
  tool: string;
  data: Data;
  headcount?: number | null;
  onQuickMessage: (text: string) => void;
}) {
  if (data?.error) {
    return <ErrorNote text={data.error} note={data.note} />;
  }

  switch (tool) {
    case "find_venues": {
      const venues: ConciergeVenue[] = data.venues ?? [];
      if (venues.length === 0) return data.note ? <ErrorNote text={data.note} /> : null;
      return (
        <div className="flex flex-wrap gap-2.5">
          {venues.map((v) => (
            <VenueCard key={v.restaurant_id} venue={v} headcount={headcount} onQuickMessage={onQuickMessage} />
          ))}
        </div>
      );
    }

    case "check_table_availability": {
      const slots: ConciergeSlot[] = data.slots ?? [];
      return (
        <div className="space-y-2">
          {data.note && <ErrorNote text={data.note} />}
          {slots.length > 0 && (
            <div className="flex flex-wrap gap-2.5">
              {slots.map((s, i) => (
                <SlotCard key={i} slot={s} restaurantName={data.restaurant_name} onQuickMessage={onQuickMessage} />
              ))}
            </div>
          )}
        </div>
      );
    }

    case "find_supplies": {
      const found: ConciergeSupplyItem[] = data.found ?? [];
      return (
        <div className="space-y-2">
          {found.length > 0 && (
            <div className="flex flex-wrap gap-2.5">
              {found.map((item) => (
                <ProductCard key={item.spin_id ?? item.query} item={item} onQuickMessage={onQuickMessage} />
              ))}
            </div>
          )}
          {data.not_found?.length > 0 && (
            <ErrorNote text={`Not found: ${data.not_found.join(", ")}`} note={data.not_found_note} />
          )}
        </div>
      );
    }

    case "find_food": {
      const restaurants = data.restaurants ?? [];
      if (restaurants.length === 0) return null;
      return (
        <div className="flex flex-wrap gap-2.5">
          {/* eslint-disable-next-line @typescript-eslint/no-explicit-any */}
          {restaurants.map((r: any) => (
            <RestaurantCard key={r.restaurant_id} restaurant={r} onQuickMessage={onQuickMessage} />
          ))}
        </div>
      );
    }

    case "browse_menu": {
      const categories = data.categories ?? [];
      if (categories.length === 0) return null;
      return <MenuCard restaurantName={data.restaurant_name} categories={categories} onQuickMessage={onQuickMessage} />;
    }

    case "book_table":
      return data.booking ? <OrderConfirmation record={data.booking} /> : null;

    case "order_supplies":
    case "place_food_order":
      return data.order ? <OrderConfirmation record={data.order} /> : null;

    case "get_budget_summary":
      return <BudgetSummaryCard data={data} />;

    default:
      return null; // narration already covers this tool's result in prose
  }
}
