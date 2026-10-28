import React, { useCallback, useEffect, useId, useState } from 'react';
import { getHostelLocationsApi } from '../api/locations';
import { errorMessage } from '../api/client';
import { HostelNode, WingNode, FloorNode } from '../types';
import { Alert, Button, SelectField, Skeleton } from './ui';

export interface SelectedLocationDetails {
  hostelId: number;
  hostelName: string;
  wingId: number;
  wingName: string;
  floorId: number;
  floorName: string;
}

export interface LocationPickerProps {
  value?: number | null; // Selected floor_id
  onChange: (floorId: number | null, details?: SelectedLocationDetails | null) => void;
  disabled?: boolean;
  required?: boolean;
  error?: string | null;
  onBlur?: () => void;
  className?: string;
  idPrefix?: string;
}

export function LocationPicker({
  value,
  onChange,
  disabled = false,
  required = false,
  error,
  onBlur,
  className,
  idPrefix,
}: LocationPickerProps) {
  const generatedId = useId();
  const prefix = idPrefix || generatedId;

  const [locations, setLocations] = useState<HostelNode[]>([]);
  const [loadStatus, setLoadStatus] = useState<'loading' | 'ready' | 'error'>('loading');
  const [loadError, setLoadError] = useState<string | null>(null);

  const [hostelId, setHostelId] = useState<string>('');
  const [wingId, setWingId] = useState<string>('');
  const [floorId, setFloorId] = useState<string>('');

  const loadLocations = useCallback((signal?: AbortSignal) => {
    setLoadStatus('loading');
    setLoadError(null);
    getHostelLocationsApi(signal)
      .then((data) => {
        setLocations(data);
        setLoadStatus('ready');
      })
      .catch((err) => {
        if (signal?.aborted) return;
        setLoadError(errorMessage(err, 'Could not load hostel locations.'));
        setLoadStatus('error');
      });
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    loadLocations(controller.signal);
    return () => controller.abort();
  }, [loadLocations]);

  // Sync internal state when external `value` (floor_id) changes or when locations load
  useEffect(() => {
    if (!value || locations.length === 0) {
      if (!value) {
        setFloorId('');
      }
      return;
    }

    // Locate the floor node across all hostels and wings
    for (const h of locations) {
      for (const w of h.wings) {
        const matchingFloor = w.floors.find((f) => f.id === value);
        if (matchingFloor) {
          setHostelId(String(h.id));
          setWingId(String(w.id));
          setFloorId(String(matchingFloor.id));
          return;
        }
      }
    }
  }, [value, locations]);

  // Derived active items
  const selectedHostel = locations.find((h) => String(h.id) === hostelId) || null;
  const availableWings: WingNode[] = selectedHostel ? selectedHostel.wings : [];
  const selectedWing = availableWings.find((w) => String(w.id) === wingId) || null;
  const availableFloors: FloorNode[] = selectedWing ? selectedWing.floors : [];

  const handleHostelChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const newHostelId = e.target.value;
    setHostelId(newHostelId);
    // Cascade reset child selections
    setWingId('');
    setFloorId('');
    onChange(null, null);
  };

  const handleWingChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const newWingId = e.target.value;
    setWingId(newWingId);
    // Cascade reset floor selection
    setFloorId('');
    onChange(null, null);
  };

  const handleFloorChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const newFloorId = e.target.value;
    setFloorId(newFloorId);

    if (!newFloorId) {
      onChange(null, null);
      return;
    }

    const fid = Number(newFloorId);
    const floorNode = availableFloors.find((f) => f.id === fid);
    if (floorNode && selectedHostel && selectedWing) {
      onChange(fid, {
        hostelId: selectedHostel.id,
        hostelName: selectedHostel.name,
        wingId: selectedWing.id,
        wingName: selectedWing.name,
        floorId: floorNode.id,
        floorName: floorNode.name,
      });
    } else {
      onChange(fid, null);
    }
  };

  if (loadStatus === 'loading') {
    return (
      <div className={`location-picker location-picker--loading ${className || ''}`.trim()}>
        <div className="field">
          <span className="field__label">
            Hostel location {required ? <span className="field__required">*</span> : null}
          </span>
          <Skeleton height={46} />
        </div>
      </div>
    );
  }

  if (loadStatus === 'error') {
    return (
      <div className={`location-picker location-picker--error ${className || ''}`.trim()}>
        <Alert
          tone="error"
          title="Couldn't load hostel locations"
          action={
            <Button size="sm" variant="secondary" icon="refresh" onClick={() => loadLocations()}>
              Retry
            </Button>
          }
        >
          {loadError}
        </Alert>
      </div>
    );
  }

  if (locations.length === 0) {
    return (
      <div className={`location-picker location-picker--empty ${className || ''}`.trim()}>
        <p className="field__hint">No active hostel locations are currently configured.</p>
      </div>
    );
  }

  return (
    <div className={`location-picker ${className || ''}`.trim()}>
      <div className="accommodation-grid">
        <SelectField
          label="Hostel building"
          name={`${prefix}-hostel`}
          value={hostelId}
          onChange={handleHostelChange}
          onBlur={onBlur}
          required={required}
          disabled={disabled}
        >
          <option value="">Choose a hostel</option>
          {locations.map((h) => (
            <option key={h.id} value={h.id}>
              {h.name}
            </option>
          ))}
        </SelectField>

        <SelectField
          label="Wing / Block"
          name={`${prefix}-wing`}
          value={wingId}
          onChange={handleWingChange}
          onBlur={onBlur}
          required={required}
          disabled={disabled || !hostelId}
          hint={!hostelId ? 'Select a hostel first' : undefined}
        >
          <option value="">Choose a wing</option>
          {availableWings.map((w) => (
            <option key={w.id} value={w.id}>
              {w.name}
            </option>
          ))}
        </SelectField>

        <SelectField
          label="Floor"
          name={`${prefix}-floor`}
          value={floorId}
          onChange={handleFloorChange}
          onBlur={onBlur}
          required={required}
          disabled={disabled || !wingId}
          error={error}
          hint={!wingId ? 'Select a wing first' : undefined}
        >
          <option value="">Choose a floor</option>
          {availableFloors.map((f) => (
            <option key={f.id} value={f.id}>
              {f.name}
            </option>
          ))}
        </SelectField>
      </div>
    </div>
  );
}

