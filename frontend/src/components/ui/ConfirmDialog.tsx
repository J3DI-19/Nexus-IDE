import React, { useEffect } from 'react';
import { ClipboardCopy, X, AlertTriangle } from 'lucide-react';

interface ConfirmDialogProps {
  isOpen: boolean;
  title: string;
  description: string;
  confirmText?: string;
  cancelText?: string;
  hideCancel?: boolean;
  secondaryText?: string;
  onSecondaryAction?: () => void;
  onConfirm: () => void;
  onCancel: () => void;
  variant?: 'default' | 'destructive';
  loading?: boolean;
}

const ConfirmDialog: React.FC<ConfirmDialogProps> = ({
  isOpen,
  title,
  description,
  confirmText = 'Confirm',
  cancelText = 'Cancel',
  hideCancel = false,
  secondaryText,
  onSecondaryAction,
  onConfirm,
  onCancel,
  variant = 'default',
  loading = false
}) => {
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (!isOpen) return;
      if (e.key === 'Escape') onCancel();
      if (e.key === 'Enter' && !loading) onConfirm();
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onCancel, onConfirm, loading]);

  if (!isOpen) return null;

  return (
    <div className="modal-overlay" onClick={onCancel}>
      <div 
        className="modal-content"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="modal-body">
          <div className="modal-flex">
            <div className={`modal-icon-box ${variant}`}>
              {variant === 'destructive' ? <AlertTriangle size={20} /> : <X size={20} style={{ transform: 'rotate(45deg)' }} />}
            </div>
            <div className="modal-text-content">
              <h3 className="modal-title">
                {title}
              </h3>
              <p className="modal-description">
                {description}
              </p>
            </div>
          </div>
        </div>

        <div className="modal-footer">
          {onSecondaryAction && secondaryText && (
            <button
              onClick={onSecondaryAction}
              disabled={loading}
              className="modal-btn modal-btn-secondary"
              type="button"
            >
              <ClipboardCopy size={12} />
              {secondaryText}
            </button>
          )}
          {!hideCancel && (
            <button
              onClick={onCancel}
              disabled={loading}
              className="modal-btn modal-btn-cancel"
            >
              {cancelText}
            </button>
          )}
          <button
            onClick={onConfirm}
            disabled={loading}
            className={`modal-btn modal-btn-confirm ${variant}`}
          >
            {loading ? 'Processing...' : confirmText}
          </button>
        </div>
      </div>
    </div>
  );
};

export default ConfirmDialog;
