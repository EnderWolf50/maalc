// Native HTML drag and drop for a set of sortable items (the gift list tab's tiles and its purchase order dialog). An item can
// only be dropped on another of its group. The Tauri window needs "dragDropEnabled": false for this (see ReorderList in ui.tsx).
import { useRef, useState, type DragEvent } from "react";

/** `item(key, group)` gives the props of one draggable element; `move(from, to, group)` runs when `from` is dropped on `to`.
 * `canDrag` can refuse a drag (and say why) before it starts. */
export function useDragSort(move: (from: string, to: string, group: string) => void, canDrag: () => boolean = () => true) {
  const drag = useRef<{ key: string; group: string } | null>(null);
  const [over, setOver] = useState<string | null>(null);
  const [dragging, setDragging] = useState<string | null>(null);
  return (key: string, group: string) => {
    const accepts = () => drag.current !== null && drag.current.key !== key && drag.current.group === group;
    return {
      draggable: true,
      "data-over": over === key || undefined,
      "data-dragging": dragging === key || undefined,
      onDragStart(e: DragEvent) {
        e.stopPropagation();
        if (!canDrag()) return e.preventDefault();
        drag.current = { key, group };
        setDragging(key);
        e.dataTransfer.setData("text/plain", key);
        e.dataTransfer.effectAllowed = "move";
      },
      onDragOver(e: DragEvent) {
        if (!accepts()) return;
        e.preventDefault();
        e.stopPropagation();
        setOver(key);
      },
      onDragLeave() { setOver((o) => (o === key ? null : o)); },
      onDrop(e: DragEvent) {
        if (!accepts()) return;
        e.preventDefault();
        e.stopPropagation();
        const from = drag.current!.key;
        drag.current = null;
        setOver(null);
        move(from, key, group);
      },
      onDragEnd() { drag.current = null; setOver(null); setDragging(null); },
    };
  };
}
