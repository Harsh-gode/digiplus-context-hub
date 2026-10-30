import { CalendarClock, CornerDownRight } from "lucide-react";
import { fmtDate } from "../api";
import { PriorityBadge, SourceTag, StatusBadge } from "./ui";

export default function ItemTable({ items, onOpen, showMeeting = false, meetingTitles = {} }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-xs text-slate-500 border-b border-slate-100">
            <th className="py-2 px-3 font-medium">Item</th>
            <th className="py-2 px-3 font-medium">Owner</th>
            <th className="py-2 px-3 font-medium">Due</th>
            <th className="py-2 px-3 font-medium">Status</th>
            {showMeeting && <th className="py-2 px-3 font-medium">Tracked in</th>}
          </tr>
        </thead>
        <tbody>
          {items.map((i) => (
            <tr key={i.id} onClick={() => onOpen(i.id)} className="border-b border-slate-50 hover:bg-brand-50/40 cursor-pointer">
              <td className="py-2.5 px-3">
                <div className={`font-medium ${["done", "dropped"].includes(i.status) ? "text-slate-400 line-through" : ""}`}>{i.title}</div>
                <div className="flex gap-1 mt-1 flex-wrap">
                  <PriorityBadge priority={i.priority} />
                  <SourceTag source={i.source} />
                  {i.times_carried > 0 && (
                    <span className={`chip ${i.times_carried >= 2 ? "bg-orange-100 text-orange-700" : "bg-orange-50 text-orange-600"}`} title="Times carried forward to a later meeting">
                      <CornerDownRight className="w-3 h-3" />{i.times_carried}×
                    </span>
                  )}
                </div>
              </td>
              <td className="py-2.5 px-3 whitespace-nowrap">{i.owner || <span className="text-red-500 text-xs font-medium">Unassigned</span>}</td>
              <td className={`py-2.5 px-3 whitespace-nowrap ${i.is_overdue ? "text-red-600 font-medium" : ""}`}>
                {i.is_overdue && <CalendarClock className="w-3.5 h-3.5 inline mr-1" />}
                {fmtDate(i.due_date)}
              </td>
              <td className="py-2.5 px-3"><StatusBadge status={i.status} /></td>
              {showMeeting && <td className="py-2.5 px-3 text-xs text-slate-500 max-w-48 truncate">{meetingTitles[i.current_meeting_id] || `#${i.current_meeting_id}`}</td>}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
