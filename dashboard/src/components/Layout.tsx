import { useEffect, useState } from 'react'
import { NavLink, Outlet } from 'react-router-dom'

const NAV = [
  { to: '/', label: 'Pipeline', end: true },
  { to: '/jobs', label: 'Job Queue' },
  { to: '/profiles', label: 'Profiles' },
  { to: '/settings', label: 'Settings' },
  { to: '/console', label: 'Agent Console' },
]

export function Layout() {
  const [dark, setDark] = useState(() => {
    if (typeof window === 'undefined') return false
    return localStorage.getItem('seejob-theme') === 'dark'
  })

  useEffect(() => {
    document.documentElement.classList.toggle('dark', dark)
    localStorage.setItem('seejob-theme', dark ? 'dark' : 'light')
  }, [dark])

  return (
    <div className="flex min-h-screen">
      <aside className="flex w-56 flex-shrink-0 flex-col border-r border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900">
        <div className="border-b border-slate-200 px-4 py-5 dark:border-slate-800">
          <h1 className="text-lg font-bold tracking-tight text-indigo-600 dark:text-indigo-400">
            SeeJob
          </h1>
          <p className="text-xs text-slate-500">Control Dashboard</p>
        </div>
        <nav className="flex-1 space-y-1 p-3">
          {NAV.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) =>
                `block rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
                  isActive
                    ? 'bg-indigo-50 text-indigo-700 dark:bg-indigo-950/50 dark:text-indigo-300'
                    : 'text-slate-600 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-slate-800'
                }`
              }
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
        <div className="border-t border-slate-200 p-3 dark:border-slate-800">
          <button
            type="button"
            onClick={() => setDark((d) => !d)}
            className="w-full rounded-lg px-3 py-2 text-left text-sm text-slate-600 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-slate-800"
          >
            {dark ? '☀️ Light mode' : '🌙 Dark mode'}
          </button>
        </div>
      </aside>
      <main className="flex min-h-0 flex-1 flex-col overflow-auto p-4 md:p-6 lg:p-8">
        <Outlet />
      </main>
    </div>
  )
}
