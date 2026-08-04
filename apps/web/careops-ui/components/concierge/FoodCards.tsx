"use client";

interface FoodRestaurant {
  restaurant_id: string;
  name?: string;
  avg_rating?: number;
  cost_for_two?: number;
  delivery_time?: string;
  cuisines?: string[];
}

interface MenuItem {
  item_id: string;
  name: string;
  price: number;
  veg?: boolean;
}

interface MenuCategory {
  category: string;
  items: MenuItem[];
}

export function RestaurantCard({
  restaurant,
  onQuickMessage,
}: {
  restaurant: FoodRestaurant;
  onQuickMessage: (text: string) => void;
}) {
  return (
    <div className="card w-full max-w-sm px-4 py-3.5">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="truncate text-[13.5px] font-semibold text-[var(--color-text-primary)]">{restaurant.name ?? "Restaurant"}</p>
          <div className="mt-1 flex flex-wrap items-center gap-1.5 text-[11px] text-[var(--color-text-faint)]">
            {restaurant.avg_rating != null && (
              <span className="inline-flex items-center gap-0.5 font-semibold text-[var(--color-accent)]">★ {restaurant.avg_rating}</span>
            )}
            {restaurant.delivery_time && <span>· {restaurant.delivery_time}</span>}
          </div>
        </div>
        {restaurant.cost_for_two != null && (
          <div className="shrink-0 text-right">
            <p className="text-[9px] uppercase tracking-[0.14em] text-[var(--color-text-ghost)]">Cost for two</p>
            <p className="text-[13px] font-bold text-[var(--color-text-primary)]">Rs.{Math.round(restaurant.cost_for_two)}</p>
          </div>
        )}
      </div>

      {restaurant.cuisines && restaurant.cuisines.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1">
          {restaurant.cuisines.slice(0, 4).map((c) => (
            <span key={c} className="rounded-full bg-[var(--color-surface-sunken)] px-2 py-0.5 text-[10px] text-[var(--color-text-soft)]">{c}</span>
          ))}
        </div>
      )}

      <button
        onClick={() => onQuickMessage(`Show me the menu at ${restaurant.name ?? "this restaurant"}.`)}
        className="mt-3 w-full rounded-lg border border-[var(--color-border-default)] bg-[var(--color-surface-raised)] py-1.5 text-[11.5px] font-semibold text-[var(--color-text-primary)] transition-colors hover:border-[var(--color-accent)] hover:text-[var(--color-accent)]"
      >
        View menu
      </button>
    </div>
  );
}

export function MenuCard({
  restaurantName,
  categories,
  onQuickMessage,
}: {
  restaurantName?: string;
  categories: MenuCategory[];
  onQuickMessage: (text: string) => void;
}) {
  return (
    <div className="card w-full max-w-sm px-4 py-3.5">
      {restaurantName && (
        <p className="mb-2.5 truncate text-[13px] font-semibold text-[var(--color-text-primary)]">{restaurantName}</p>
      )}
      <div className="space-y-3.5">
        {categories.map((cat, ci) => (
          <div key={`${cat.category}-${ci}`}>
            <p className="text-[9.5px] font-bold uppercase tracking-[0.14em] text-[var(--color-text-ghost)]">{cat.category}</p>
            <div className="mt-1.5 space-y-1.5">
              {cat.items.map((item, ii) => (
                <div key={`${item.item_id || item.name}-${ii}`} className="flex items-center justify-between gap-2 rounded-lg px-2 py-1.5 hover:bg-[var(--color-surface-sunken)]">
                  <div className="flex min-w-0 items-center gap-1.5">
                    {item.veg != null && (
                      <span className={`h-2.5 w-2.5 shrink-0 rounded-sm border ${item.veg ? "border-emerald-500" : "border-rose-500"}`}>
                        <span className={`block h-full w-full scale-50 rounded-full ${item.veg ? "bg-emerald-500" : "bg-rose-500"}`} />
                      </span>
                    )}
                    <span className="truncate text-[12.5px] text-[var(--color-text-primary)]">{item.name}</span>
                  </div>
                  <div className="flex shrink-0 items-center gap-2">
                    <span className="text-[12px] font-semibold text-[var(--color-text-soft)]">Rs.{Math.round(item.price)}</span>
                    <button
                      onClick={() => onQuickMessage(`Add ${item.name} to my food cart.`)}
                      className="rounded-md border border-[var(--color-border-default)] px-2 py-0.5 text-[10.5px] font-semibold text-[var(--color-text-faint)] transition-colors hover:border-[var(--color-accent)] hover:text-[var(--color-accent)]"
                    >
                      Add
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
