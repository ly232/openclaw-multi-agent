import { Routes, Route, NavLink } from "react-router-dom"
import { LayoutDashboard, Users, Bot, MessageSquare, BarChart3, Database } from "lucide-react"
import { cn } from "./lib/utils"
import Dashboard from "./pages/Dashboard"
import Accounts from "./pages/Accounts"
import Agents from "./pages/Agents"
import Messages from "./pages/Messages"
import Evaluations from "./pages/Evaluations"
import DuckDB from "./pages/DuckDB"

const nav = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard },
  { to: "/accounts", label: "Accounts", icon: Users },
  { to: "/agents", label: "Agents", icon: Bot },
  { to: "/messages", label: "Messages", icon: MessageSquare },
  { to: "/evaluations", label: "Evaluations", icon: BarChart3 },
  { to: "/duckdb", label: "DuckDB", icon: Database },
]

export default function App() {
  return (
    <div className="flex h-screen">
      <aside className="w-56 border-r bg-white dark:bg-gray-900 p-4 flex flex-col gap-1">
        <h1 className="text-lg font-bold mb-4 px-2">OpenClaw</h1>
        {nav.map(({ to, label, icon: Icon }) => (
          <NavLink
            key={to}
            to={to}
            end={to === "/"}
            className={({ isActive }) =>
              cn(
                "flex items-center gap-2 px-3 py-2 rounded-md text-sm transition-colors",
                isActive
                  ? "bg-blue-100 dark:bg-blue-900 text-blue-700 dark:text-blue-300"
                  : "hover:bg-gray-100 dark:hover:bg-gray-800"
              )
            }
          >
            <Icon size={16} />
            <span>{label}</span>
          </NavLink>
        ))}
      </aside>
      <main className="flex-1 overflow-y-auto p-6">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/accounts" element={<Accounts />} />
          <Route path="/agents" element={<Agents />} />
          <Route path="/messages" element={<Messages />} />
          <Route path="/messages/:id" element={<Messages />} />
          <Route path="/evaluations" element={<Evaluations />} />
          <Route path="/duckdb" element={<DuckDB />} />
        </Routes>
      </main>
    </div>
  )
}
