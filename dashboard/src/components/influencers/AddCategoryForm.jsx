import React, { useState } from 'react';
import { Plus } from 'lucide-react';
import { toast } from 'sonner';
import Input from '../common/Input';
import Button from '../common/Button';
import { createCategory } from '../../services/influencerService';

export default function AddCategoryForm({ onCreated }) {
  const [name, setName] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!name.trim() || submitting) return;
    setSubmitting(true);
    try {
      await createCategory(name.trim());
      toast.success(`Category "${name.trim()}" added`);
      setName('');
      onCreated();
    } catch {
      // apiClient's interceptor already toasts the error detail.
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="flex items-end gap-3">
      <div className="flex-1 min-w-0">
        <label className="text-xs font-medium block mb-1.5" style={{ color: 'var(--color-text-secondary)' }}>
          New category
        </label>
        <Input placeholder="e.g. Fashion & Lifestyle" value={name} onChange={(e) => setName(e.target.value)} />
      </div>
      <Button type="submit" size="md" loading={submitting} disabled={!name.trim()}>
        <Plus className="w-3.5 h-3.5" />
        Add category
      </Button>
    </form>
  );
}
