import React, { useEffect, useState } from 'react';
import { Command } from 'cmdk';
import { useNavigate } from 'react-router-dom';
import { Search, Monitor, Users, Activity, LogOut, Image, Sparkles, DatabaseBackup, UserPlus } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { useAppStore } from '../../store/useAppStore';

export default function CommandPalette() {
  const [open, setOpen] = useState(false);
  const navigate = useNavigate();
  const clearApiKey = useAppStore((s) => s.clearApiKey);

  useEffect(() => {
    const down = (e) => {
      if (e.key === 'k' && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        setOpen((open) => !open);
      }
    };
    document.addEventListener('keydown', down);
    return () => document.removeEventListener('keydown', down);
  }, []);

  const runCommand = (command) => {
    setOpen(false);
    command();
  };

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="fixed inset-0 z-50 flex items-start justify-center pt-[15vh]"
          style={{ background: 'var(--color-bg-overlay)', backdropFilter: 'blur(4px)' }}
          onClick={() => setOpen(false)}
        >
          <motion.div
            initial={{ opacity: 0, scale: 0.95, y: -20 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95, y: -20 }}
            transition={{ type: 'spring', damping: 20, stiffness: 300 }}
            onClick={(e) => e.stopPropagation()}
            className="w-full max-w-lg overflow-hidden glass-panel"
          >
            <Command
              className="w-full bg-transparent flex flex-col"
              onKeyDown={(e) => {
                if (e.key === 'Escape') setOpen(false);
              }}
            >
              <div className="flex items-center px-4 py-3 border-b border-[var(--color-border-subtle)]">
                <Search className="w-5 h-5 text-[var(--color-text-muted)] mr-3" />
                <Command.Input
                  autoFocus
                  placeholder="Type a command or search..."
                  className="w-full bg-transparent text-[var(--color-text-primary)] outline-none placeholder:text-[var(--color-text-muted)] text-sm"
                />
              </div>

              <Command.List className="max-h-[300px] overflow-y-auto p-2 scrollbar-thin">
                <Command.Empty className="p-4 text-center text-sm text-[var(--color-text-muted)]">
                  No results found.
                </Command.Empty>

                <Command.Group heading="Navigation" className="text-xs font-semibold text-[var(--color-text-muted)] px-2 py-2">
                  <Command.Item
                    onSelect={() => runCommand(() => navigate('/'))}
                    className="flex items-center gap-2 px-3 py-2 mt-1 text-sm rounded-md cursor-pointer hover:bg-[var(--color-bg-card-hover)] aria-selected:bg-[var(--color-bg-card-hover)]"
                  >
                    <Activity className="w-4 h-4" />
                    Overview
                  </Command.Item>
                  <Command.Item
                    onSelect={() => runCommand(() => navigate('/influencers'))}
                    className="flex items-center gap-2 px-3 py-2 mt-1 text-sm rounded-md cursor-pointer hover:bg-[var(--color-bg-card-hover)] aria-selected:bg-[var(--color-bg-card-hover)]"
                  >
                    <Users className="w-4 h-4" />
                    Influencers
                  </Command.Item>
                  <Command.Item
                    onSelect={() => runCommand(() => navigate('/content'))}
                    className="flex items-center gap-2 px-3 py-2 mt-1 text-sm rounded-md cursor-pointer hover:bg-[var(--color-bg-card-hover)] aria-selected:bg-[var(--color-bg-card-hover)]"
                  >
                    <Image className="w-4 h-4" />
                    Content
                  </Command.Item>
                  <Command.Item
                    onSelect={() => runCommand(() => navigate('/insights'))}
                    className="flex items-center gap-2 px-3 py-2 mt-1 text-sm rounded-md cursor-pointer hover:bg-[var(--color-bg-card-hover)] aria-selected:bg-[var(--color-bg-card-hover)]"
                  >
                    <Sparkles className="w-4 h-4" />
                    Insights
                  </Command.Item>
                  <Command.Item
                    onSelect={() => runCommand(() => navigate('/query'))}
                    className="flex items-center gap-2 px-3 py-2 mt-1 text-sm rounded-md cursor-pointer hover:bg-[var(--color-bg-card-hover)] aria-selected:bg-[var(--color-bg-card-hover)]"
                  >
                    <Monitor className="w-4 h-4" />
                    Query Console
                  </Command.Item>
                  <Command.Item
                    onSelect={() => runCommand(() => navigate('/accounts'))}
                    className="flex items-center gap-2 px-3 py-2 mt-1 text-sm rounded-md cursor-pointer hover:bg-[var(--color-bg-card-hover)] aria-selected:bg-[var(--color-bg-card-hover)]"
                  >
                    <UserPlus className="w-4 h-4" />
                    Accounts
                  </Command.Item>
                  <Command.Item
                    onSelect={() => runCommand(() => navigate('/export'))}
                    className="flex items-center gap-2 px-3 py-2 mt-1 text-sm rounded-md cursor-pointer hover:bg-[var(--color-bg-card-hover)] aria-selected:bg-[var(--color-bg-card-hover)]"
                  >
                    <DatabaseBackup className="w-4 h-4" />
                    Export
                  </Command.Item>
                </Command.Group>

                <Command.Group heading="Actions" className="text-xs font-semibold text-[var(--color-text-muted)] px-2 py-2 mt-2 border-t border-[var(--color-border-subtle)]">
                  <Command.Item
                    onSelect={() => runCommand(clearApiKey)}
                    className="flex items-center gap-2 px-3 py-2 mt-1 text-sm rounded-md cursor-pointer hover:bg-[var(--color-bg-card-hover)] aria-selected:bg-[var(--color-bg-card-hover)] text-[var(--color-danger)]"
                  >
                    <LogOut className="w-4 h-4" />
                    Disconnect
                  </Command.Item>
                </Command.Group>
              </Command.List>
            </Command>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
