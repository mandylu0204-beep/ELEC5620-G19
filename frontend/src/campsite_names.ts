// IDs identify the catalogue record. Historical records keep their original names.
const names:Record<string,string>={
  'the-basin':'The Basin campground',
  'bonnie-vale':'Bonnie Vale campground',
  'bents-basin':'Bents Basin campground',
  cattai:'Cattai campground',
  euroka:'Euroka campground',
  'lane-cove':'Lane Cove caravan park',
  'putty-beach':'Putty Beach campground',
  'little-beach':'Little Beach campground',
  'tallow-beach':'Tallow Beach campground',
  'cockatoo-island':'Cockatoo Island waterfront campground',
  'demo-pine-camp':'Demo Pine Camp','demo-river-flat':'Demo River Flat','demo-ridge-lookout':'Demo Ridge Lookout',
  'demo-fern-walk':'Demo Fern Walk','demo-lake-meadow':'Demo Lake Meadow','demo-sandstone-grove':'Demo Sandstone Grove',
  'demo-cloud-gully':'Demo Cloud Gully','demo-wattle-rest':'Demo Wattle Rest','demo-granite-ledge':'Demo Granite Ledge',
  'demo-moonlit-field':'Demo Moonlit Field',
};

export const campName=(id:string)=>names[id]??id;
