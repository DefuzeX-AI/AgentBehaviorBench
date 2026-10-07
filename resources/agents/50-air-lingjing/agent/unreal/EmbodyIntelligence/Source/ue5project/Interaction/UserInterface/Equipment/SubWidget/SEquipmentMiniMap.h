#pragma once

#include "CoreMinimal.h"
#include "Widgets/SCompoundWidget.h"
#include "Widgets/Layout/SScrollBox.h"

class SEquipmentMiniMap : public SCompoundWidget
{
public:
	SLATE_BEGIN_ARGS(SEquipmentMiniMap) {}
	SLATE_END_ARGS()

	void Construct(const FArguments& InArgs);

	void AddTrajectoryPoint(const FVector2D& InPoint);
	void ClearTrajectory();

private:
	TArray<FVector2D> TrajectoryPoints;
	
};
