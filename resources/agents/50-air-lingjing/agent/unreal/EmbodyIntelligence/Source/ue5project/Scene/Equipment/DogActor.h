// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "EquipmentActor.h"
#include "DogActor.generated.h"

/*


*/
UCLASS()
class UE5PROJECT_API ADogActor : public AEquipmentActor
{
	GENERATED_BODY()

public:
	ADogActor();


	void SetDogScale(double InScale);

protected:

	virtual FSColor GetTagWidgetColor() const override;

	virtual FString GetImageSaveSubdir() const override;
};
