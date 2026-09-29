export function ticketStars(data:{difficulty_stars?:number;difficulty?:string}):number{
  const value=Number(data.difficulty_stars);
  if(Number.isInteger(value)&&value>=1&&value<=5)return value;
  return data.difficulty==='Сложный'?5:data.difficulty==='Средний'?3:1;
}

export function legacyDifficulty(stars:number):string{
  return stars<=2?'Базовый':stars===3?'Средний':'Сложный';
}

export function starLabel(stars:number):string{
  return '★'.repeat(stars)+'☆'.repeat(5-stars);
}
