"use client";

import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

/** A single-value select over a value → label map (Base UI needs `items` to render the label). */
export function PickOne({
  label,
  value,
  items,
  onChange,
  className,
}: {
  label: string;
  value: string | null;
  items: Record<string, string>;
  onChange: (value: string | null) => void;
  className?: string;
}) {
  return (
    <Select value={value} onValueChange={onChange} items={items}>
      <SelectTrigger aria-label={label} className={className}>
        <SelectValue placeholder={label} />
      </SelectTrigger>
      <SelectContent>
        {Object.entries(items).map(([v, text]) => (
          <SelectItem key={v} value={v}>
            {text}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
