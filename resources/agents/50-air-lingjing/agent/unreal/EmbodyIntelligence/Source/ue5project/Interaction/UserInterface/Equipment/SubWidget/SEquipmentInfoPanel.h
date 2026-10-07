#pragma once

#include "CoreMinimal.h"
#include "Widgets/SCompoundWidget.h"
#include "ue5project/Scene/Equipment/EquipmentStruct.h"

class SEquipmentInfoPanel : public SCompoundWidget
{
public:
	SLATE_BEGIN_ARGS(SEquipmentInfoPanel) {}
	SLATE_ARGUMENT(FEquipmentInfo, EquipmentInfo)	
	SLATE_END_ARGS()

	void Construct(const FArguments& InArgs);

	void UpdateTransform(const FTransform& InTransform);

private:
	FString EquipmentTypeStr;
	FString EquipmentId;
	FString EquipmentName;
	FVector Location = FVector::ZeroVector;
	FRotator Rotation = FRotator::ZeroRotator;
	FVector Scale = FVector::OneVector;

};
