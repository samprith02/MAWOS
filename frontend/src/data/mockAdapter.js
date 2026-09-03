// The existing FastAPI API does not expose library, event, or administrative
// settings endpoints. Keeping provisional presentation data here prevents
// unsupported contracts and scattered hard-coded values in page components.
export const unavailableStudentServices = {
  library: { issued: 0, fine: 0, note: 'Library details are not yet exposed by the MAWOS API.' },
  event: { title: 'No event data available', note: 'Event check-in requires an API endpoint.' },
};

export const unavailableAdminControls = [
  'User and permission management', 'Infrastructure monitoring',
  'Dataset, backup, and deployment controls',
];
