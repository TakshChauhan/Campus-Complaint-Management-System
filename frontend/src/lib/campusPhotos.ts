/**
 * The two DAU campus photographs supplied for the project, exported at two widths
 * (WebP). Vite fingerprints these files in production builds.
 */
import lotus960 from '../assets/campus/lotus-pond-960.webp';
import lotus1920 from '../assets/campus/lotus-pond-1920.webp';
import aerial960 from '../assets/campus/campus-aerial-960.webp';
import aerial1920 from '../assets/campus/campus-aerial-1920.webp';

export interface CampusPhoto {
  id: string;
  src: string;
  srcSet: string;
  /** Place name shown in the caption. */
  caption: string;
  /** object-position that keeps the subject in frame when cropped. */
  position: string;
}

export const LOTUS_POND: CampusPhoto = {
  id: 'lotus-pond',
  src: lotus1920,
  srcSet: `${lotus960} 960w, ${lotus1920} 1600w`,
  caption: 'Lotus pond, DAU Gandhinagar',
  // Panorama: keep the egret on the stone ring and the lotus flowers in frame.
  position: '47% 62%',
};

export const CAMPUS_AERIAL: CampusPhoto = {
  id: 'campus-aerial',
  src: aerial1920,
  srcSet: `${aerial960} 960w, ${aerial1920} 1920w`,
  caption: 'Academic blocks from above',
  position: '45% 55%',
};

export const CAMPUS_PHOTOS: CampusPhoto[] = [LOTUS_POND, CAMPUS_AERIAL];
